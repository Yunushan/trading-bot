#include "NativeLlmAdvisory.h"

#include "NativeOrderSafety.h"

#include <QJsonArray>
#include <QJsonDocument>

namespace {

QString nonEmptyOr(const QString &value, const QString &fallback) {
    const QString text = value.trimmed();
    return text.isEmpty() ? fallback : text;
}

bool containsAny(const QString &text, const QStringList &phrases) {
    for (const QString &phrase : phrases) {
        if (text.contains(phrase, Qt::CaseInsensitive)) {
            return true;
        }
    }
    return false;
}

void scanStructuredPolicyValue(const QJsonValue &value, QStringList &violations) {
    if (value.isObject()) {
        const QJsonObject object = value.toObject();
        for (auto it = object.constBegin(); it != object.constEnd(); ++it) {
            const QString key = it.key();
            const QString item = it.value().isString()
                ? it.value().toString().trimmed().toLower()
                : QString::fromUtf8(QJsonDocument(it.value().toObject()).toJson(QJsonDocument::Compact)).trimmed().toLower();
            if (key == QStringLiteral("action")
                && (item == QStringLiteral("place_order") || item == QStringLiteral("submit_order") || item == QStringLiteral("execute_order"))
                && !violations.contains(QStringLiteral("direct_order_action"))) {
                violations.append(QStringLiteral("direct_order_action"));
            }
            if ((key == QStringLiteral("execution_status") || key == QStringLiteral("order_status") || key == QStringLiteral("status"))
                && (item == QStringLiteral("executed") || item == QStringLiteral("filled") || item == QStringLiteral("submitted"))
                && !violations.contains(QStringLiteral("order_execution_claim"))) {
                violations.append(QStringLiteral("order_execution_claim"));
            }
            if ((key == QStringLiteral("disable_stop_loss") || key == QStringLiteral("risk_override") || key == QStringLiteral("override_risk"))
                && (item == QStringLiteral("1") || item == QStringLiteral("true") || item == QStringLiteral("yes") || item == QStringLiteral("on"))
                && !violations.contains(QStringLiteral("risk_override"))) {
                violations.append(QStringLiteral("risk_override"));
            }
            if (key == QStringLiteral("stop_loss_enabled")
                && (item == QStringLiteral("0") || item == QStringLiteral("false") || item == QStringLiteral("no") || item == QStringLiteral("off"))
                && !violations.contains(QStringLiteral("risk_override"))) {
                violations.append(QStringLiteral("risk_override"));
            }
            scanStructuredPolicyValue(it.value(), violations);
        }
    } else if (value.isArray()) {
        for (const QJsonValue &item : value.toArray()) {
            scanStructuredPolicyValue(item, violations);
        }
    }
}

QStringList orderedViolations(const QStringList &violations) {
    QStringList out;
    for (const QString &label : {
             QStringLiteral("direct_order_action"),
             QStringLiteral("order_execution_claim"),
             QStringLiteral("risk_override"),
         }) {
        if (violations.contains(label)) {
            out.append(label);
        }
    }
    return out;
}

} // namespace

namespace NativeLlmAdvisory {

QString executionBoundaryText() {
    return QStringLiteral(
        "Execution boundary: this LLM is advisory only. It must not place orders, "
        "claim that an order was executed, or override deterministic strategy, risk, "
        "take-profit, or stop-loss logic.");
}

QJsonObject buildPromptRoutePayload(
    const QString &prompt,
    const QString &systemPrompt,
    bool dryRun,
    const QString &source) {
    return {
        {QStringLiteral("prompt"), prompt.trimmed()},
        {QStringLiteral("system_prompt"), systemPrompt.trimmed()},
        {QStringLiteral("dry_run"), dryRun},
        {QStringLiteral("source"), nonEmptyOr(source, QStringLiteral("cpp-desktop-llm"))},
    };
}

QJsonObject buildLocalModelRoutePayload(
    const QString &baseUrl,
    const QString &model,
    const QString &source) {
    return {
        {QStringLiteral("base_url"), nonEmptyOr(baseUrl, QStringLiteral("http://127.0.0.1:11434/v1"))},
        {QStringLiteral("model"), model.trimmed()},
        {QStringLiteral("source"), nonEmptyOr(source, QStringLiteral("cpp-desktop-llm-local-model"))},
    };
}

QString describeLocalModelStatus(const QJsonObject &status, const QString &fallbackModel) {
    const QString model = nonEmptyOr(status.value(QStringLiteral("model")).toString(), fallbackModel);
    const QString installed = status.value(QStringLiteral("installed")).toBool(false)
        ? QStringLiteral("installed")
        : QStringLiteral("not installed");
    const QString serverKind = nonEmptyOr(status.value(QStringLiteral("server_kind")).toString(), QStringLiteral("local server"));
    const QString size = status.value(QStringLiteral("estimated_size_label")).toString().trimmed().isEmpty()
        ? QString()
        : QStringLiteral(", estimated %1").arg(status.value(QStringLiteral("estimated_size_label")).toString().trimmed());
    QString storage = status.value(QStringLiteral("storage_hint")).toString().trimmed();
    const QJsonArray storagePaths = status.value(QStringLiteral("storage_paths")).toArray();
    if (!storagePaths.isEmpty()) {
        QStringList paths;
        for (const QJsonValue &path : storagePaths) {
            const QString text = path.toString().trimmed();
            if (!text.isEmpty()) {
                paths.append(text);
            }
        }
        if (!paths.isEmpty()) {
            storage = paths.join(QStringLiteral("; "));
        }
    }
    if (storage.isEmpty()) {
        storage = QStringLiteral("Ollama model cache outside this project.");
    }
    const QString warning = status.value(QStringLiteral("disk_space_warning")).toString().trimmed().isEmpty()
        ? QString()
        : QStringLiteral(" %1").arg(status.value(QStringLiteral("disk_space_warning")).toString().trimmed());
    const QString error = status.value(QStringLiteral("error")).toString().trimmed().isEmpty()
        ? QString()
        : QStringLiteral(" Server check: %1").arg(NativeOrderSafety::redactText(status.value(QStringLiteral("error")).toString()));
    return QStringLiteral("Local model '%1' is %2 on %3%4. Storage: %5.%6%7")
        .arg(model, installed, serverKind, size, storage, warning, error);
}

QStringList outputPolicyViolations(const QString &text) {
    const QString lower = text.trimmed().toLower();
    if (lower.isEmpty()) {
        return {};
    }
    QStringList violations;
    const QJsonDocument document = QJsonDocument::fromJson(text.toUtf8());
    if (!document.isNull()) {
        scanStructuredPolicyValue(document.isObject() ? QJsonValue(document.object()) : QJsonValue(document.array()), violations);
    }
    if (containsAny(lower, {
            QStringLiteral("order executed"),
            QStringLiteral("trade executed"),
            QStringLiteral("i executed"),
            QStringLiteral("i placed an order"),
            QStringLiteral("i submitted an order"),
            QStringLiteral("submitted the order"),
        }) && !violations.contains(QStringLiteral("order_execution_claim"))) {
        violations.append(QStringLiteral("order_execution_claim"));
    }
    if (containsAny(lower, {
            QStringLiteral("\"action\":\"place_order\""),
            QStringLiteral("\"action\": \"place_order\""),
            QStringLiteral("\"action\":\"submit_order\""),
            QStringLiteral("\"action\": \"submit_order\""),
            QStringLiteral("place_order"),
            QStringLiteral("submit_order"),
            QStringLiteral("execute_order"),
        }) && !violations.contains(QStringLiteral("direct_order_action"))) {
        violations.append(QStringLiteral("direct_order_action"));
    }
    if (containsAny(lower, {
            QStringLiteral("disable stop loss"),
            QStringLiteral("disabled stop loss"),
            QStringLiteral("override risk"),
            QStringLiteral("set leverage to"),
            QStringLiteral("changed leverage"),
        }) && !violations.contains(QStringLiteral("risk_override"))) {
        violations.append(QStringLiteral("risk_override"));
    }
    return orderedViolations(violations);
}

QJsonObject renderPromptResult(const QJsonObject &response) {
    const QString rawText = nonEmptyOr(
        response.value(QStringLiteral("text")).toString(),
        nonEmptyOr(response.value(QStringLiteral("response")).toString(), response.value(QStringLiteral("error")).toString()));
    const QString safeText = NativeOrderSafety::redactText(rawText);
    const QStringList violations = outputPolicyViolations(safeText);
    QJsonArray violationArray;
    for (const QString &violation : violations) {
        violationArray.append(violation);
    }
    const bool ok = response.value(QStringLiteral("ok")).toBool(response.value(QStringLiteral("error")).isUndefined()) && violations.isEmpty();
    const bool dryRun = response.value(QStringLiteral("dry_run")).toBool(false);
    return {
        {QStringLiteral("ok"), ok},
        {QStringLiteral("dry_run"), dryRun},
        {QStringLiteral("status"), ok
             ? (dryRun ? QStringLiteral("LLM advisory dry run ok") : QStringLiteral("LLM advisory: ok"))
             : QStringLiteral("LLM advisory request failed")},
        {QStringLiteral("text"), safeText},
        {QStringLiteral("violations"), violationArray},
        {QStringLiteral("execution_boundary"), executionBoundaryText()},
    };
}

} // namespace NativeLlmAdvisory
