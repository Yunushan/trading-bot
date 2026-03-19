#include "TradingBotWindow.h"
#include "TradingBotWindow.dashboard_runtime_shared.h"

#include <QComboBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDoubleSpinBox>
#include <QFormLayout>
#include <QLineEdit>
#include <QSpinBox>
#include <QVBoxLayout>
#include <QVector>

namespace {
struct IndicatorDialogFieldSpec {
    QString key;
    QString label;
    enum Kind { IntField, DoubleField, ComboField } kind;
    double min = -999999.0;
    double max = 999999.0;
    double step = 1.0;
    QVariant defaultValue;
    QStringList options;
};

struct IndicatorDialogBoundField {
    QString key;
    IndicatorDialogFieldSpec::Kind kind;
    QWidget *widget = nullptr;
    bool nullableText = false;
};

QVector<IndicatorDialogFieldSpec> indicatorDialogFieldSpecs(const QString &indicatorKey) {
    QVector<IndicatorDialogFieldSpec> fields;
    auto addBuySell = [&fields]() {
        fields.push_back({
            QStringLiteral("buy_value"),
            QStringLiteral("buy_value"),
            IndicatorDialogFieldSpec::DoubleField,
            -999999.0,
            999999.0,
            0.1,
            QVariant(),
            {},
        });
        fields.push_back({
            QStringLiteral("sell_value"),
            QStringLiteral("sell_value"),
            IndicatorDialogFieldSpec::DoubleField,
            -999999.0,
            999999.0,
            0.1,
            QVariant(),
            {},
        });
    };

    if (indicatorKey == QStringLiteral("ma")) {
        fields = {
            {QStringLiteral("length"), QStringLiteral("length"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 20, {}},
            {QStringLiteral("type"), QStringLiteral("type"), IndicatorDialogFieldSpec::ComboField, 0, 0, 0, QStringLiteral("SMA"), {QStringLiteral("SMA"), QStringLiteral("EMA"), QStringLiteral("WMA"), QStringLiteral("VWMA")}},
        };
        addBuySell();
    } else if (indicatorKey == QStringLiteral("donchian")) {
        fields = {
            {QStringLiteral("length"), QStringLiteral("length"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 20, {}},
        };
        addBuySell();
    } else if (indicatorKey == QStringLiteral("psar")) {
        fields = {
            {QStringLiteral("af"), QStringLiteral("af"), IndicatorDialogFieldSpec::DoubleField, 0.0, 10.0, 0.01, 0.02, {}},
            {QStringLiteral("max_af"), QStringLiteral("max_af"), IndicatorDialogFieldSpec::DoubleField, 0.0, 10.0, 0.01, 0.2, {}},
        };
        addBuySell();
    } else if (indicatorKey == QStringLiteral("bb")) {
        fields = {
            {QStringLiteral("length"), QStringLiteral("length"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 20, {}},
            {QStringLiteral("std"), QStringLiteral("std"), IndicatorDialogFieldSpec::DoubleField, 0.1, 50.0, 0.1, 2.0, {}},
        };
        addBuySell();
    } else if (indicatorKey == QStringLiteral("rsi")) {
        fields = {
            {QStringLiteral("length"), QStringLiteral("length"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 14, {}},
        };
        addBuySell();
    } else if (indicatorKey == QStringLiteral("volume")) {
        addBuySell();
    } else if (indicatorKey == QStringLiteral("stoch_rsi") || indicatorKey == QStringLiteral("stochastic")) {
        fields = {
            {QStringLiteral("length"), QStringLiteral("length"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 14, {}},
            {QStringLiteral("smooth_k"), QStringLiteral("smooth_k"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 3, {}},
            {QStringLiteral("smooth_d"), QStringLiteral("smooth_d"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 3, {}},
        };
        addBuySell();
    } else if (indicatorKey == QStringLiteral("willr")) {
        fields = {
            {QStringLiteral("length"), QStringLiteral("length"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 14, {}},
        };
        addBuySell();
    } else if (indicatorKey == QStringLiteral("macd")) {
        fields = {
            {QStringLiteral("fast"), QStringLiteral("fast"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 12, {}},
            {QStringLiteral("slow"), QStringLiteral("slow"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 26, {}},
            {QStringLiteral("signal"), QStringLiteral("signal"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 9, {}},
        };
        addBuySell();
    } else if (indicatorKey == QStringLiteral("uo")) {
        fields = {
            {QStringLiteral("short"), QStringLiteral("short"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 7, {}},
            {QStringLiteral("medium"), QStringLiteral("medium"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 14, {}},
            {QStringLiteral("long"), QStringLiteral("long"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 28, {}},
        };
        addBuySell();
    } else if (indicatorKey == QStringLiteral("adx") || indicatorKey == QStringLiteral("dmi")) {
        fields = {
            {QStringLiteral("length"), QStringLiteral("length"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 14, {}},
        };
        addBuySell();
    } else if (indicatorKey == QStringLiteral("supertrend")) {
        fields = {
            {QStringLiteral("atr_period"), QStringLiteral("atr_period"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 10, {}},
            {QStringLiteral("multiplier"), QStringLiteral("multiplier"), IndicatorDialogFieldSpec::DoubleField, 0.1, 50.0, 0.1, 3.0, {}},
        };
        addBuySell();
    } else {
        fields = {
            {QStringLiteral("length"), QStringLiteral("length"), IndicatorDialogFieldSpec::IntField, 1, 10000, 1.0, 20, {}},
        };
        addBuySell();
    }

    return fields;
}

void applyStoredIndicatorDefaults(QVector<IndicatorDialogFieldSpec> &fields, const QVariantMap &storedParams) {
    for (IndicatorDialogFieldSpec &field : fields) {
        if (!storedParams.contains(field.key)) {
            continue;
        }
        const QVariant value = storedParams.value(field.key);
        field.defaultValue = value.isValid() ? value : QVariant();
    }
}

QString indicatorDialogStyleSheet(bool isLight) {
    const QString bg = isLight ? QStringLiteral("#ffffff") : QStringLiteral("#0f1624");
    const QString fg = isLight ? QStringLiteral("#0f172a") : QStringLiteral("#e5e7eb");
    const QString fieldBg = isLight ? QStringLiteral("#ffffff") : QStringLiteral("#0d1117");
    const QString border = isLight ? QStringLiteral("#cbd5e1") : QStringLiteral("#1f2937");
    const QString btnBg = isLight ? QStringLiteral("#e5e7eb") : QStringLiteral("#111827");
    const QString btnHover = isLight ? QStringLiteral("#dbeafe") : QStringLiteral("#1f2937");

    return QStringLiteral(
               "QDialog { background-color: %1; color: %2; }"
               "QLabel { color: %2; font-weight: 500; }"
               "QSpinBox, QComboBox, QLineEdit { background: %3; color: %2; border: 1px solid %4; border-radius: 4px; padding: 4px 6px; }"
               "QComboBox QAbstractItemView { background: %3; color: %2; selection-background-color: %4; }"
               "QDialogButtonBox QPushButton { background: %5; color: %2; border: 1px solid %4; border-radius: 4px; padding: 4px 12px; min-width: 68px; }"
               "QDialogButtonBox QPushButton:hover { background: %6; }")
        .arg(bg, fg, fieldBg, border, btnBg, btnHover);
}

QVariant indicatorDialogFieldValue(const IndicatorDialogBoundField &bound) {
    if (!bound.widget || bound.key.trimmed().isEmpty()) {
        return QVariant();
    }

    if (bound.nullableText) {
        const QString text = qobject_cast<QLineEdit *>(bound.widget)
                                 ? qobject_cast<QLineEdit *>(bound.widget)->text().trimmed()
                                 : QString();
        if (text.isEmpty() || text.compare(QStringLiteral("none"), Qt::CaseInsensitive) == 0) {
            return QVariant();
        }
        bool ok = false;
        const double parsed = text.toDouble(&ok);
        return ok ? QVariant(parsed) : QVariant(text);
    }

    if (bound.kind == IndicatorDialogFieldSpec::IntField) {
        if (const auto *spin = qobject_cast<QSpinBox *>(bound.widget)) {
            return spin->value();
        }
        return QVariant();
    }
    if (bound.kind == IndicatorDialogFieldSpec::DoubleField) {
        if (const auto *spin = qobject_cast<QDoubleSpinBox *>(bound.widget)) {
            return spin->value();
        }
        return QVariant();
    }
    if (const auto *combo = qobject_cast<QComboBox *>(bound.widget)) {
        return combo->currentText();
    }
    return QVariant();
}
} // namespace

void TradingBotWindow::showIndicatorDialog(const QString &indicatorName) {
    const bool isLight = dashboardThemeCombo_
        && dashboardThemeCombo_->currentText().compare(QStringLiteral("Light"), Qt::CaseInsensitive) == 0;
    const QString indicatorKey = TradingBotWindowDashboardRuntime::normalizedIndicatorKey(indicatorName);

    QVector<IndicatorDialogFieldSpec> fields = indicatorDialogFieldSpecs(indicatorKey);
    applyStoredIndicatorDefaults(fields, dashboardIndicatorParams_.value(indicatorKey));

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

    QVector<IndicatorDialogBoundField> boundFields;
    boundFields.reserve(fields.size());

    for (const IndicatorDialogFieldSpec &spec : fields) {
        QWidget *fieldWidget = nullptr;
        switch (spec.kind) {
            case IndicatorDialogFieldSpec::IntField: {
                auto *spin = new QSpinBox(dialog);
                spin->setRange(static_cast<int>(spec.min), static_cast<int>(spec.max));
                spin->setSingleStep(static_cast<int>(spec.step));
                spin->setValue(spec.defaultValue.isValid() ? spec.defaultValue.toInt() : 0);
                spin->setMinimumWidth(160);
                fieldWidget = spin;
                break;
            }
            case IndicatorDialogFieldSpec::DoubleField: {
                auto *spin = new QDoubleSpinBox(dialog);
                spin->setRange(spec.min, spec.max);
                spin->setDecimals(6);
                spin->setSingleStep(spec.step);
                spin->setValue(spec.defaultValue.isValid() ? spec.defaultValue.toDouble() : 0.0);
                spin->setMinimumWidth(160);
                spin->setSpecialValueText(tr("None"));
                fieldWidget = spin;
                break;
            }
            case IndicatorDialogFieldSpec::ComboField: {
                auto *combo = new QComboBox(dialog);
                combo->addItems(spec.options);
                if (spec.defaultValue.isValid()) {
                    const int idx = combo->findText(spec.defaultValue.toString(), Qt::MatchFixedString);
                    if (idx >= 0) {
                        combo->setCurrentIndex(idx);
                    }
                }
                combo->setMinimumWidth(160);
                fieldWidget = combo;
                break;
            }
        }

        const bool nullableText = spec.key == QStringLiteral("buy_value") || spec.key == QStringLiteral("sell_value");
        if (nullableText) {
            auto *edit = new QLineEdit(dialog);
            edit->setPlaceholderText(tr("None"));
            edit->setMinimumWidth(160);
            if (spec.defaultValue.isValid()) {
                edit->setText(spec.defaultValue.toString());
            }
            fieldWidget = edit;
        }

        form->addRow(spec.label, fieldWidget);
        boundFields.push_back({spec.key, spec.kind, fieldWidget, nullableText});
    }

    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, dialog);
    connect(buttons, &QDialogButtonBox::accepted, dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject);

    auto *layout = new QVBoxLayout(dialog);
    layout->addLayout(form);
    layout->addWidget(buttons, 0, Qt::AlignRight);

    dialog->setStyleSheet(indicatorDialogStyleSheet(isLight));
    dialog->resize(360, dialog->sizeHint().height());

    if (dialog->exec() != QDialog::Accepted) {
        return;
    }

    QVariantMap updated = dashboardIndicatorParams_.value(indicatorKey);
    for (const IndicatorDialogBoundField &bound : boundFields) {
        updated.insert(bound.key, indicatorDialogFieldValue(bound));
    }
    dashboardIndicatorParams_.insert(indicatorKey, updated);
}
