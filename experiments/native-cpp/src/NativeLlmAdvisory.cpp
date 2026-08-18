#include "NativeLlmAdvisory.h"

#include "NativeOrderSafety.h"
#include "generated/PythonParityContract.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QHash>
#include <QHostAddress>
#include <QUrl>
#include <QVector>

#include <algorithm>

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

QString jsonScalarText(const QJsonValue &value) {
    if (value.isString()) {
        return value.toString();
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("True") : QStringLiteral("False");
    }
    if (value.isDouble()) {
        return QString::number(value.toDouble(), 'g', 16);
    }
    return QString();
}

QString jsonStringLiteral(const QString &value) {
    QJsonArray wrapper;
    wrapper.append(value);
    const QByteArray encoded = QJsonDocument(wrapper).toJson(QJsonDocument::Compact);
    return QString::fromUtf8(encoded.mid(1, encoded.size() - 2));
}

QString canonicalJsonText(const QJsonValue &value) {
    if (value.isObject()) {
        const QJsonObject object = value.toObject();
        QStringList keys = object.keys();
        std::sort(keys.begin(), keys.end());
        QStringList entries;
        entries.reserve(keys.size());
        for (const QString &key : keys) {
            entries.append(
                jsonStringLiteral(key) + QStringLiteral(":") + canonicalJsonText(object.value(key)));
        }
        return QStringLiteral("{") + entries.join(QStringLiteral(",")) + QStringLiteral("}");
    }
    if (value.isArray()) {
        QStringList entries;
        for (const QJsonValue &item : value.toArray()) {
            entries.append(canonicalJsonText(item));
        }
        return QStringLiteral("[") + entries.join(QStringLiteral(",")) + QStringLiteral("]");
    }
    if (value.isString()) {
        return jsonStringLiteral(value.toString());
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    }
    if (value.isNull() || value.isUndefined()) {
        return QStringLiteral("null");
    }
    QJsonArray wrapper;
    wrapper.append(value);
    const QByteArray encoded = QJsonDocument(wrapper).toJson(QJsonDocument::Compact);
    return QString::fromUtf8(encoded.mid(1, encoded.size() - 2));
}

bool isSensitiveKey(const QString &key) {
    QString normalized;
    for (const QChar character : key.trimmed().toLower()) {
        if (character.isLetterOrNumber()) {
            normalized.append(character);
        }
    }
    if (normalized.endsWith(QStringLiteral("env"))
        || normalized.endsWith(QStringLiteral("environment"))
        || normalized.endsWith(QStringLiteral("present"))) {
        return false;
    }
    for (const QString &part : {
             QStringLiteral("apikey"),
             QStringLiteral("apisecret"),
             QStringLiteral("authorization"),
             QStringLiteral("bearer"),
             QStringLiteral("passphrase"),
             QStringLiteral("password"),
             QStringLiteral("privatekey"),
             QStringLiteral("secret"),
             QStringLiteral("signature"),
             QStringLiteral("token"),
             QStringLiteral("xmbxapikey"),
         }) {
        if (normalized.contains(part)) {
            return true;
        }
    }
    return false;
}

QJsonValue redactJsonValue(const QJsonValue &value, int depth = 0) {
    if (depth > 8) {
        return QStringLiteral("...");
    }
    if (value.isObject()) {
        const QJsonObject source = value.toObject();
        QJsonObject output;
        for (auto it = source.constBegin(); it != source.constEnd(); ++it) {
            if (isSensitiveKey(it.key())) {
                output.insert(
                    it.key(),
                    it.value().isNull() || (it.value().isString() && it.value().toString().isEmpty())
                        ? QJsonValue(QString())
                        : QJsonValue(QStringLiteral("<redacted>")));
            } else {
                output.insert(it.key(), redactJsonValue(it.value(), depth + 1));
            }
        }
        return output;
    }
    if (value.isArray()) {
        QJsonArray output;
        for (const QJsonValue &item : value.toArray()) {
            output.append(redactJsonValue(item, depth + 1));
        }
        return output;
    }
    if (value.isString()) {
        return NativeOrderSafety::redactText(value.toString());
    }
    return value;
}

QJsonObject objectValue(const QJsonValue &value) {
    return value.isObject() ? value.toObject() : QJsonObject{};
}

QJsonValue nullableValue(const QJsonValue &value) {
    return value.isUndefined() ? QJsonValue(QJsonValue::Null) : value;
}

int mappingItemCount(const QJsonValue &value) {
    if (value.isObject()) {
        return value.toObject().size();
    }
    if (value.isArray()) {
        return value.toArray().size();
    }
    return 0;
}

QJsonObject minimalObject(const QJsonValue &value, const QStringList &keys) {
    const QJsonObject source = objectValue(value);
    QJsonObject output;
    for (const QString &key : keys) {
        if (source.contains(key)) {
            output.insert(key, redactJsonValue(source.value(key)));
        }
    }
    return output;
}

QJsonValue cloudSafeContext(const QJsonValue &context) {
    if (!context.isObject() || context.toObject().isEmpty()) {
        return QJsonValue();
    }
    const QJsonObject source = context.toObject();
    const QJsonObject runtime = objectValue(source.value(QStringLiteral("runtime")));
    const QJsonObject status = objectValue(source.value(QStringLiteral("status")));
    const QJsonObject execution = objectValue(source.value(QStringLiteral("execution")));
    const QJsonObject config = objectValue(source.value(QStringLiteral("config")));
    const QJsonObject portfolio = objectValue(source.value(QStringLiteral("portfolio")));
    const QJsonArray logs = source.value(QStringLiteral("logs")).isArray()
        ? source.value(QStringLiteral("logs")).toArray()
        : QJsonArray{};

    QJsonObject configSummary{
        {QStringLiteral("mode"), redactJsonValue(nullableValue(config.value(QStringLiteral("mode"))))},
        {QStringLiteral("selected_exchange"), redactJsonValue(nullableValue(config.value(QStringLiteral("selected_exchange"))))},
        {QStringLiteral("account_type"), redactJsonValue(nullableValue(config.value(QStringLiteral("account_type"))))},
        {QStringLiteral("symbol_count"), mappingItemCount(config.value(QStringLiteral("symbols")))},
        {QStringLiteral("interval_count"), mappingItemCount(config.value(QStringLiteral("intervals")))},
        {QStringLiteral("llm"), config.value(QStringLiteral("llm")).isObject()
             ? redactJsonValue(config.value(QStringLiteral("llm")))
             : QJsonObject{}},
        {QStringLiteral("raw_config_redacted"), true},
    };
    QJsonObject portfolioSummary{
        {QStringLiteral("open_position_count"), mappingItemCount(portfolio.value(QStringLiteral("open_position_records")))},
        {QStringLiteral("closed_position_count"), mappingItemCount(portfolio.value(QStringLiteral("closed_position_records")))},
        {QStringLiteral("active_pnl"), redactJsonValue(nullableValue(portfolio.value(QStringLiteral("active_pnl"))))},
        {QStringLiteral("closed_pnl"), redactJsonValue(nullableValue(portfolio.value(QStringLiteral("closed_pnl"))))},
        {QStringLiteral("position_records_redacted"), true},
    };
    return QJsonObject{
        {QStringLiteral("privacy_notice"), QStringLiteral("Cloud LLM context minimized; credentials, raw config, logs, and position records are redacted.")},
        {QStringLiteral("runtime"), minimalObject(runtime, {QStringLiteral("phase"), QStringLiteral("control_plane")})},
        {QStringLiteral("status"), minimalObject(status, {QStringLiteral("lifecycle_phase"), QStringLiteral("runtime_active"), QStringLiteral("active_engine_count")})},
        {QStringLiteral("execution"), minimalObject(execution, {QStringLiteral("state"), QStringLiteral("workload_kind"), QStringLiteral("active_engine_count"), QStringLiteral("last_action")})},
        {QStringLiteral("config_summary"), configSummary},
        {QStringLiteral("portfolio_summary"), portfolioSummary},
        {QStringLiteral("logs"), QJsonObject{{QStringLiteral("count"), logs.size()}, {QStringLiteral("redacted"), true}}},
    };
}

bool baseUrlUsesPublicNetwork(const QString &baseUrl) {
    const QUrl parsed(baseUrl.trimmed());
    const QString host = parsed.host().trimmed();
    if (host.isEmpty()) {
        return false;
    }
    const QString lowered = host.toLower();
    if (lowered == QStringLiteral("localhost") || lowered.endsWith(QStringLiteral(".local"))) {
        return false;
    }
    QHostAddress address;
    if (!address.setAddress(host)) {
        return true;
    }
    if (address.isLoopback()) {
        return false;
    }
    if (address.isInSubnet(QHostAddress(QStringLiteral("10.0.0.0")), 8)
        || address.isInSubnet(QHostAddress(QStringLiteral("172.16.0.0")), 12)
        || address.isInSubnet(QHostAddress(QStringLiteral("192.168.0.0")), 16)
        || address.isInSubnet(QHostAddress(QStringLiteral("169.254.0.0")), 16)
        || address.isInSubnet(QHostAddress(QStringLiteral("fc00::")), 7)
        || address.isInSubnet(QHostAddress(QStringLiteral("fe80::")), 10)) {
        return false;
    }
    return true;
}

const PythonParityContract::PythonLlmProvider *providerForKey(const QString &key) {
    for (const auto &provider : PythonParityContract::kPythonLlmProviders) {
        if (QString::fromUtf8(provider.key.data(), static_cast<int>(provider.key.size())) == key) {
            return &provider;
        }
    }
    return nullptr;
}

QString normalizeProviderKey(const QString &value) {
    const QString raw = value.trimmed().toLower().replace(QChar('_'), QChar('-'));
    for (const auto &choice : PythonParityContract::kPythonLlmProviderChoices) {
        if (QString::fromUtf8(choice.key.data(), static_cast<int>(choice.key.size())) == raw) {
            const QString normalized = QString::fromUtf8(choice.value.data(), static_cast<int>(choice.value.size()));
            return providerForKey(normalized) ? normalized : QStringLiteral("openai");
        }
    }
    return providerForKey(raw) ? raw : QStringLiteral("openai");
}

QStringList csvValues(std::string_view value) {
    QStringList values;
    for (const QString &item : QString::fromUtf8(value.data(), static_cast<int>(value.size())).split(',')) {
        const QString normalized = item.trimmed().toLower();
        if (!normalized.isEmpty() && !values.contains(normalized)) {
            values.append(normalized);
        }
    }
    return values;
}

QString normalizeReasoningEffort(const PythonParityContract::PythonLlmProvider &provider, const QString &value) {
    const QStringList efforts = csvValues(provider.reasoningEfforts);
    if (efforts.isEmpty()) {
        return QStringLiteral("default");
    }
    const QString defaultEffort = QString::fromUtf8(
        provider.defaultReasoningEffort.data(), static_cast<int>(provider.defaultReasoningEffort.size()))
                                      .trimmed()
                                      .toLower();
    const QString raw = value.trimmed().toLower().replace(QChar('_'), QChar('-'));
    QString normalized = raw;
    if (raw.isEmpty()) {
        normalized = defaultEffort.isEmpty() ? efforts.first() : defaultEffort;
    } else if (raw == QStringLiteral("auto")) {
        normalized = QStringLiteral("default");
    } else if (raw == QStringLiteral("off") || raw == QStringLiteral("no") || raw == QStringLiteral("false")) {
        normalized = efforts.contains(QStringLiteral("none")) ? QStringLiteral("none") : QStringLiteral("disabled");
    } else if (raw == QStringLiteral("extra-high")) {
        normalized = QStringLiteral("xhigh");
    }
    return efforts.contains(normalized)
        ? normalized
        : (defaultEffort.isEmpty() ? efforts.first() : defaultEffort);
}

QJsonObject openAiReasoningBody(const QString &provider, const QString &model, const QString &effort) {
    if (effort.isEmpty() || effort == QStringLiteral("default")) {
        return {};
    }
    if (provider == QStringLiteral("deepseek")) {
        if (effort == QStringLiteral("none") || effort == QStringLiteral("disabled") || effort == QStringLiteral("off")) {
            return QJsonObject{{QStringLiteral("thinking"), QJsonObject{{QStringLiteral("type"), QStringLiteral("disabled")}}}};
        }
        QJsonObject body{{QStringLiteral("thinking"), QJsonObject{{QStringLiteral("type"), QStringLiteral("enabled")}}}};
        if (QStringList{QStringLiteral("high"), QStringLiteral("max"), QStringLiteral("xhigh"), QStringLiteral("low"), QStringLiteral("medium")}.contains(effort)) {
            body.insert(QStringLiteral("reasoning_effort"), (effort == QStringLiteral("max") || effort == QStringLiteral("xhigh")) ? QStringLiteral("max") : effort);
        }
        return body;
    }
    if (provider == QStringLiteral("qwen")) {
        return QJsonObject{{QStringLiteral("enable_thinking"), effort != QStringLiteral("none") && effort != QStringLiteral("disabled") && effort != QStringLiteral("off")}};
    }
    if (provider == QStringLiteral("moonshot")) {
        const QString normalizedModel = model.trimmed().toLower();
        if (normalizedModel.startsWith(QStringLiteral("kimi-k3"))) {
            return effort == QStringLiteral("max") ? QJsonObject{{QStringLiteral("reasoning_effort"), QStringLiteral("max")}} : QJsonObject{};
        }
        if (normalizedModel.startsWith(QStringLiteral("kimi-k2.5")) || normalizedModel.startsWith(QStringLiteral("kimi-k2.6"))) {
            if (effort == QStringLiteral("none") || effort == QStringLiteral("disabled") || effort == QStringLiteral("off")) {
                return QJsonObject{{QStringLiteral("thinking"), QJsonObject{{QStringLiteral("type"), QStringLiteral("disabled")}}}};
            }
            if (QStringList{QStringLiteral("enabled"), QStringLiteral("low"), QStringLiteral("medium"), QStringLiteral("high"), QStringLiteral("max"), QStringLiteral("xhigh")}.contains(effort)) {
                return QJsonObject{{QStringLiteral("thinking"), QJsonObject{{QStringLiteral("type"), QStringLiteral("enabled")}}}};
            }
        }
    }
    return QJsonObject{{QStringLiteral("reasoning_effort"), effort}};
}

QJsonObject anthropicThinkingBody(const QString &effort) {
    if (effort.isEmpty() || effort == QStringLiteral("default")) {
        return {};
    }
    if (effort == QStringLiteral("none") || effort == QStringLiteral("disabled") || effort == QStringLiteral("off")) {
        return QJsonObject{{QStringLiteral("thinking"), QJsonObject{{QStringLiteral("type"), QStringLiteral("disabled")}}}};
    }
    const QHash<QString, int> budgets{
        {QStringLiteral("enabled"), 2048},
        {QStringLiteral("low"), 2048},
        {QStringLiteral("medium"), 4096},
        {QStringLiteral("high"), 8192},
    };
    if (!budgets.contains(effort)) {
        return {};
    }
    const int budget = budgets.value(effort);
    return QJsonObject{
        {QStringLiteral("max_tokens"), std::max(1024, budget + 1024)},
        {QStringLiteral("thinking"), QJsonObject{{QStringLiteral("type"), QStringLiteral("enabled")}, {QStringLiteral("budget_tokens"), budget}}},
    };
}

QJsonObject geminiGenerationConfig(const QString &effort, const QString &model) {
    if (effort.isEmpty() || effort == QStringLiteral("default")) {
        return {};
    }
    QString thinkingLevel = (effort == QStringLiteral("none") || effort == QStringLiteral("disabled") || effort == QStringLiteral("minimal"))
        ? QStringLiteral("minimal")
        : effort;
    if (model.startsWith(QStringLiteral("gemini-3-pro"))
        && (thinkingLevel == QStringLiteral("minimal") || thinkingLevel == QStringLiteral("medium"))) {
        thinkingLevel = thinkingLevel == QStringLiteral("minimal") ? QStringLiteral("low") : QStringLiteral("high");
    }
    if (!QStringList{QStringLiteral("minimal"), QStringLiteral("low"), QStringLiteral("medium"), QStringLiteral("high")}.contains(thinkingLevel)) {
        return {};
    }
    return QJsonObject{{QStringLiteral("thinkingConfig"), QJsonObject{{QStringLiteral("thinkingLevel"), thinkingLevel}}}};
}

QString joinUrl(const QString &baseUrl, const QString &path) {
    QString base = baseUrl.trimmed();
    while (base.endsWith('/')) {
        base.chop(1);
    }
    QString suffix = path.trimmed();
    while (suffix.startsWith('/')) {
        suffix.remove(0, 1);
    }
    return base + QStringLiteral("/") + suffix;
}

QString policyScalarText(const QJsonValue &value) {
    if (value.isString()) {
        return value.toString().trimmed().toLower();
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    }
    if (value.isDouble()) {
        return QString::number(value.toDouble(), 'g', 16).trimmed().toLower();
    }
    if (value.isObject()) {
        return QString::fromUtf8(
                   QJsonDocument(value.toObject()).toJson(QJsonDocument::Compact))
            .trimmed()
            .toLower();
    }
    if (value.isArray()) {
        return QString::fromUtf8(
                   QJsonDocument(value.toArray()).toJson(QJsonDocument::Compact))
            .trimmed()
            .toLower();
    }
    return value.isNull() ? QStringLiteral("null") : QString();
}

void scanStructuredPolicyValue(const QJsonValue &value, QStringList &violations) {
    if (value.isObject()) {
        const QJsonObject object = value.toObject();
        for (auto it = object.constBegin(); it != object.constEnd(); ++it) {
            const QString key = it.key().trimmed().toLower();
            const QString item = policyScalarText(it.value());
            if (QStringList{
                    QStringLiteral("action"),
                    QStringLiteral("command"),
                    QStringLiteral("intent"),
                    QStringLiteral("operation"),
                    QStringLiteral("tool"),
                }
                    .contains(key)) {
                if (QStringList{
                        QStringLiteral("cancel_order"),
                        QStringLiteral("change_leverage"),
                        QStringLiteral("close_position"),
                        QStringLiteral("create_order"),
                        QStringLiteral("execute_order"),
                        QStringLiteral("market_buy"),
                        QStringLiteral("market_sell"),
                        QStringLiteral("open_position"),
                        QStringLiteral("place_order"),
                        QStringLiteral("set_leverage"),
                        QStringLiteral("submit_order"),
                    }
                        .contains(item)
                    && !violations.contains(QStringLiteral("direct_order_action"))) {
                    violations.append(QStringLiteral("direct_order_action"));
                }
                if (QStringList{
                        QStringLiteral("change_leverage"),
                        QStringLiteral("disable_stop_loss"),
                        QStringLiteral("override_risk"),
                        QStringLiteral("set_leverage"),
                    }
                        .contains(item)
                    && !violations.contains(QStringLiteral("risk_override"))) {
                    violations.append(QStringLiteral("risk_override"));
                }
            }
            if ((key == QStringLiteral("execution_status") || key == QStringLiteral("order_status") || key == QStringLiteral("status"))
                && (item == QStringLiteral("executed") || item == QStringLiteral("filled") || item == QStringLiteral("order_executed") || item == QStringLiteral("placed") || item == QStringLiteral("submitted"))
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
             QStringLiteral("order_execution_claim"),
             QStringLiteral("direct_order_action"),
             QStringLiteral("risk_override"),
         }) {
        if (violations.contains(label)) {
            out.append(label);
        }
    }
    return out;
}

QVector<QJsonValue> jsonCandidatesFromText(const QString &text) {
    const QString raw = text.trimmed();
    if (raw.isEmpty()) {
        return {};
    }
    QVector<QJsonValue> candidates;
    const auto appendCandidate = [&candidates](const QString &candidate) {
        const QJsonDocument document = QJsonDocument::fromJson(candidate.toUtf8());
        if (document.isNull()) {
            return;
        }
        candidates.append(document.isObject()
                              ? QJsonValue(document.object())
                              : QJsonValue(document.array()));
    };
    appendCandidate(raw);
    if (raw.startsWith(QStringLiteral("```"))) {
        const QStringList lines = raw.split(QChar('\n'));
        if (lines.size() >= 3 && lines.last().trimmed().startsWith(QStringLiteral("```"))) {
            appendCandidate(lines.mid(1, lines.size() - 2).join(QChar('\n')).trimmed());
        }
    }
    const int objectStart = raw.indexOf(QChar('{'));
    const int objectEnd = raw.lastIndexOf(QChar('}'));
    if (objectStart >= 0 && objectEnd > objectStart) {
        appendCandidate(raw.mid(objectStart, objectEnd - objectStart + 1));
    }
    const int arrayStart = raw.indexOf(QChar('['));
    const int arrayEnd = raw.lastIndexOf(QChar(']'));
    if (arrayStart >= 0 && arrayEnd > arrayStart) {
        appendCandidate(raw.mid(arrayStart, arrayEnd - arrayStart + 1));
    }
    return candidates;
}

} // namespace

namespace NativeLlmAdvisory {

QString executionBoundaryText() {
    return QStringLiteral(
        "Execution boundary: this LLM is advisory only. It must not place orders, "
        "claim that an order was executed, or override deterministic strategy, risk, "
        "take-profit, or stop-loss logic.");
}

QJsonObject buildChatRequest(
    const QJsonObject &config,
    const QString &prompt,
    const QString &systemPrompt,
    const QJsonValue &context,
    QString *error) {
    if (error != nullptr) {
        error->clear();
    }
    const auto fail = [error](const QString &message) {
        if (error != nullptr) {
            *error = message;
        }
        return QJsonObject{};
    };

    const QString providerKey = normalizeProviderKey(jsonScalarText(config.value(QStringLiteral("llm_provider"))));
    const auto *provider = providerForKey(providerKey);
    if (provider == nullptr) {
        return fail(QStringLiteral("Unsupported LLM provider."));
    }
    const QString providerLabel = QString::fromUtf8(provider->label.data(), static_cast<int>(provider->label.size()));
    const QString mode = QString::fromUtf8(provider->mode.data(), static_cast<int>(provider->mode.size()));
    const QString protocol = QString::fromUtf8(provider->protocol.data(), static_cast<int>(provider->protocol.size()));
    const QString defaultBaseUrl = QString::fromUtf8(provider->defaultBaseUrl.data(), static_cast<int>(provider->defaultBaseUrl.size()));
    const QString defaultModel = QString::fromUtf8(provider->defaultModel.data(), static_cast<int>(provider->defaultModel.size()));
    const QString defaultApiKeyEnv = QString::fromUtf8(provider->apiKeyEnv.data(), static_cast<int>(provider->apiKeyEnv.size()));
    const QString configuredBaseUrl = jsonScalarText(config.value(QStringLiteral("llm_base_url"))).trimmed();
    const QString configuredModel = jsonScalarText(config.value(QStringLiteral("llm_model"))).trimmed();
    const QString configuredApiKeyEnv = jsonScalarText(config.value(QStringLiteral("llm_api_key_env"))).trimmed();
    const QString baseUrl = configuredBaseUrl.isEmpty() ? defaultBaseUrl : configuredBaseUrl;
    const QString model = configuredModel.isEmpty() ? defaultModel : configuredModel;
    const QString apiKeyEnv = configuredApiKeyEnv.isEmpty() ? defaultApiKeyEnv : configuredApiKeyEnv;
    const QString reasoningEffort = normalizeReasoningEffort(
        *provider,
        jsonScalarText(config.value(QStringLiteral("llm_reasoning_effort"))));
    const QJsonValue allowPublicValue = config.value(QStringLiteral("llm_allow_public_network"));
    const bool allowPublicNetwork = allowPublicValue.isBool()
        ? allowPublicValue.toBool()
        : QStringList{QStringLiteral("1"), QStringLiteral("true"), QStringLiteral("yes"), QStringLiteral("on"), QStringLiteral("enabled")}
              .contains(jsonScalarText(allowPublicValue).trimmed().toLower());
    const bool publicNetwork = allowPublicNetwork || baseUrlUsesPublicNetwork(baseUrl);

    const QString userPrompt = prompt.trimmed();
    if (userPrompt.isEmpty()) {
        return fail(QStringLiteral("LLM prompt cannot be empty."));
    }
    if (model.trimmed().isEmpty()) {
        return fail(QStringLiteral("Select an LLM model before calling %1.").arg(providerLabel));
    }
    if (mode != QStringLiteral("cloud") && baseUrlUsesPublicNetwork(baseUrl) && !allowPublicNetwork) {
        return fail(QStringLiteral("Public local/custom LLM endpoints are disabled. Enable the public network endpoint control before using this base URL."));
    }

    QString apiKey = jsonScalarText(config.value(QStringLiteral("llm_api_key"))).trimmed();
    if (apiKey.isEmpty()) {
        const QByteArray envName = apiKeyEnv.toUtf8();
        apiKey = qEnvironmentVariable(envName.constData()).trimmed();
    }

    QJsonValue contextForRequest;
    if (context.isObject() && !context.toObject().isEmpty()) {
        contextForRequest = (mode == QStringLiteral("cloud") || publicNetwork)
            ? cloudSafeContext(context)
            : context;
    }
    const bool hasContext = contextForRequest.isObject() && !contextForRequest.toObject().isEmpty();

    QJsonObject headers{{QStringLiteral("Content-Type"), QStringLiteral("application/json")}};
    QJsonObject body;
    QString url;
    if (protocol == QStringLiteral("openai-compatible") || protocol == QStringLiteral("openai-chat-completions")) {
        if (!apiKey.isEmpty()) {
            headers.insert(QStringLiteral("Authorization"), QStringLiteral("Bearer ") + apiKey);
        }
        url = joinUrl(baseUrl, QStringLiteral("chat/completions"));
        QJsonArray messages{
            QJsonObject{{QStringLiteral("role"), QStringLiteral("system")}, {QStringLiteral("content"), executionBoundaryText()}},
        };
        const QString trimmedSystemPrompt = systemPrompt.trimmed();
        if (!trimmedSystemPrompt.isEmpty()) {
            messages.append(QJsonObject{{QStringLiteral("role"), QStringLiteral("system")}, {QStringLiteral("content"), trimmedSystemPrompt}});
        }
        if (hasContext) {
            messages.append(QJsonObject{
                {QStringLiteral("role"), QStringLiteral("system")},
                {QStringLiteral("content"), QStringLiteral("Trading context JSON: ") + canonicalJsonText(contextForRequest)},
            });
        }
        messages.append(QJsonObject{{QStringLiteral("role"), QStringLiteral("user")}, {QStringLiteral("content"), userPrompt}});
        body.insert(QStringLiteral("model"), model);
        body.insert(QStringLiteral("messages"), messages);
        const QJsonObject reasoningBody = openAiReasoningBody(providerKey, model, reasoningEffort);
        for (auto it = reasoningBody.constBegin(); it != reasoningBody.constEnd(); ++it) {
            body.insert(it.key(), it.value());
        }
    } else if (protocol == QStringLiteral("anthropic-messages")) {
        if (apiKey.isEmpty()) {
            return fail(QStringLiteral("Anthropic Claude requires an API key."));
        }
        headers.insert(QStringLiteral("x-api-key"), apiKey);
        headers.insert(QStringLiteral("anthropic-version"), QStringLiteral("2023-06-01"));
        url = joinUrl(baseUrl, QStringLiteral("v1/messages"));
        QJsonArray messages{QJsonObject{{QStringLiteral("role"), QStringLiteral("user")}, {QStringLiteral("content"), userPrompt}}};
        if (hasContext) {
            messages.insert(0, QJsonObject{
                {QStringLiteral("role"), QStringLiteral("user")},
                {QStringLiteral("content"), QStringLiteral("Trading context JSON: ") + canonicalJsonText(contextForRequest)},
            });
        }
        QStringList systemParts{executionBoundaryText()};
        const QString trimmedSystemPrompt = systemPrompt.trimmed();
        if (!trimmedSystemPrompt.isEmpty()) {
            systemParts.append(trimmedSystemPrompt);
        }
        body.insert(QStringLiteral("model"), model);
        body.insert(QStringLiteral("max_tokens"), 1024);
        body.insert(QStringLiteral("messages"), messages);
        body.insert(QStringLiteral("system"), systemParts.join(QStringLiteral("\n\n")));
        const QJsonObject thinkingBody = anthropicThinkingBody(reasoningEffort);
        for (auto it = thinkingBody.constBegin(); it != thinkingBody.constEnd(); ++it) {
            body.insert(it.key(), it.value());
        }
    } else if (protocol == QStringLiteral("gemini-generate-content")) {
        if (apiKey.isEmpty()) {
            return fail(QStringLiteral("Google Gemini requires an API key."));
        }
        const QString encodedModel = QString::fromLatin1(QUrl::toPercentEncoding(model));
        const QString encodedApiKey = QString::fromLatin1(QUrl::toPercentEncoding(apiKey));
        url = joinUrl(baseUrl, QStringLiteral("models/") + encodedModel + QStringLiteral(":generateContent?key=") + encodedApiKey);
        QJsonArray parts{QJsonObject{{QStringLiteral("text"), executionBoundaryText()}}};
        const QString trimmedSystemPrompt = systemPrompt.trimmed();
        if (!trimmedSystemPrompt.isEmpty()) {
            parts.append(QJsonObject{{QStringLiteral("text"), trimmedSystemPrompt}});
        }
        if (hasContext) {
            parts.append(QJsonObject{{QStringLiteral("text"), QStringLiteral("Trading context JSON: ") + canonicalJsonText(contextForRequest)}});
        }
        parts.append(QJsonObject{{QStringLiteral("text"), userPrompt}});
        body.insert(QStringLiteral("contents"), QJsonArray{QJsonObject{{QStringLiteral("parts"), parts}}});
        const QJsonObject generationConfig = geminiGenerationConfig(reasoningEffort, model);
        if (!generationConfig.isEmpty()) {
            body.insert(QStringLiteral("generationConfig"), generationConfig);
        }
    } else {
        return fail(QStringLiteral("Unsupported LLM protocol for provider %1: %2").arg(providerKey, protocol));
    }

    return QJsonObject{
        {QStringLiteral("provider"), providerKey},
        {QStringLiteral("mode"), mode},
        {QStringLiteral("protocol"), protocol},
        {QStringLiteral("url"), url},
        {QStringLiteral("headers"), headers},
        {QStringLiteral("json"), body},
        {QStringLiteral("execution_policy"), QJsonObject{
             {QStringLiteral("advisory_only"), true},
             {QStringLiteral("can_execute_orders"), false},
             {QStringLiteral("owner"), QStringLiteral("strategy_and_risk_runtime")},
         }},
    };
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
    for (const QJsonValue &candidate : jsonCandidatesFromText(text)) {
        scanStructuredPolicyValue(candidate, violations);
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
