#include "NativeConfigPersistence.h"

#include <QDate>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSaveFile>
#include <QSet>
#include <QRegularExpression>
#include <QVector>
#include <QtGlobal>

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace {

QString currentIso(const QDateTime &timestamp = {}) {
    const QDateTime value = timestamp.isValid() ? timestamp.toUTC() : QDateTime::currentDateTimeUtc();
    return value.toString(QStringLiteral("yyyy-MM-ddTHH:mm:ss.zzz+00:00"));
}

QString envValue(const char *name) {
    return qEnvironmentVariable(name).trimmed();
}

QString expandUserPath(QString path) {
    path = path.trimmed();
    if (path == QStringLiteral("~")) {
        return QDir::homePath();
    }
    if (path.startsWith(QStringLiteral("~/")) || path.startsWith(QStringLiteral("~\\"))) {
        return QDir::homePath() + path.mid(1);
    }
    return path;
}

QString absoluteCleanPath(const QString &path) {
    const QString expanded = expandUserPath(path);
    QFileInfo info(expanded);
    if (!info.isAbsolute()) {
        info = QFileInfo(QDir::current(), expanded);
    }
    return QDir::cleanPath(info.absoluteFilePath());
}

QString comparablePath(QString path) {
    path = QDir::cleanPath(path);
#ifdef Q_OS_WIN
    path = path.toLower();
#endif
    return path;
}

bool isRelativeTo(const QString &child, const QString &parent) {
    const QString childPath = comparablePath(absoluteCleanPath(child));
    QString parentPath = comparablePath(absoluteCleanPath(parent));
    if (childPath == parentPath) {
        return true;
    }
    if (!parentPath.endsWith(QStringLiteral("/"))) {
        parentPath.append(QStringLiteral("/"));
    }
    return childPath.startsWith(parentPath);
}

bool valueHasInlineSecret(const QJsonValue &value) {
    if (value.isUndefined() || value.isNull()) {
        return false;
    }
    return !(value.isString() && value.toString().isEmpty());
}

void collectSecretFieldPaths(const QJsonValue &payload, const QString &prefix, QSet<QString> *paths) {
    if (!paths) {
        return;
    }
    if (payload.isObject()) {
        const QJsonObject object = payload.toObject();
        for (auto it = object.constBegin(); it != object.constEnd(); ++it) {
            const QString key = it.key();
            const QString path = prefix.isEmpty() ? key : QStringLiteral("%1.%2").arg(prefix, key);
            if (NativeConfigPersistence::isServiceConfigSecretKey(key) && valueHasInlineSecret(it.value())) {
                paths->insert(path);
                continue;
            }
            collectSecretFieldPaths(it.value(), path, paths);
        }
        return;
    }
    if (payload.isArray()) {
        const QJsonArray array = payload.toArray();
        for (int idx = 0; idx < array.size(); ++idx) {
            collectSecretFieldPaths(array.at(idx), QStringLiteral("%1[%2]").arg(prefix).arg(idx), paths);
        }
    }
}

QJsonArray toJsonArray(const QStringList &values) {
    QJsonArray out;
    for (const QString &value : values) {
        out.append(value);
    }
    return out;
}

QJsonValue stripInlineSecrets(const QJsonValue &payload) {
    if (payload.isObject()) {
        QJsonObject out;
        const QJsonObject object = payload.toObject();
        for (auto it = object.constBegin(); it != object.constEnd(); ++it) {
            if (NativeConfigPersistence::isServiceConfigSecretKey(it.key()) && valueHasInlineSecret(it.value())) {
                out.insert(it.key(), QString());
            } else {
                out.insert(it.key(), stripInlineSecrets(it.value()));
            }
        }
        return out;
    }
    if (payload.isArray()) {
        QJsonArray out;
        const QJsonArray array = payload.toArray();
        for (const QJsonValue &item : array) {
            out.append(stripInlineSecrets(item));
        }
        return out;
    }
    return payload;
}

bool parseFormatVersion(const QJsonValue &value, int *out) {
    if (!out) {
        return false;
    }
    if (value.isUndefined() || value.isNull()) {
        *out = NativeConfigPersistence::ServiceConfigFormatVersion;
        return true;
    }
    if (value.isDouble()) {
        const double number = value.toDouble();
        const int version = static_cast<int>(number);
        if (qFuzzyCompare(number + 1.0, static_cast<double>(version) + 1.0)) {
            *out = version;
            return true;
        }
    }
    if (value.isString()) {
        bool ok = false;
        const int version = value.toString().trimmed().toInt(&ok);
        if (ok) {
            *out = version;
            return true;
        }
    }
    return false;
}

void insertNonEmptySecretMetadata(QJsonObject *payload, const QJsonObject &metadata) {
    if (!payload) {
        return;
    }
    for (auto it = metadata.constBegin(); it != metadata.constEnd(); ++it) {
        const QJsonValue value = it.value();
        if ((value.isString() && value.toString().isEmpty())
            || (value.isArray() && value.toArray().isEmpty())
            || value.isNull()
            || value.isUndefined()) {
            continue;
        }
        payload->insert(it.key(), value);
    }
}

QString issueField(const QString &prefix, const QString &key) {
    return prefix.isEmpty() ? key : QStringLiteral("%1.%2").arg(prefix, key);
}

void addValidationIssue(QJsonArray *issues, const QString &field, const QString &message) {
    if (!issues) {
        return;
    }
    issues->append(QJsonObject{
        {QStringLiteral("field"), field},
        {QStringLiteral("message"), message},
    });
}

bool hasControlText(const QString &text) {
    static const QRegularExpression controlTextRe(QStringLiteral("[\\x00-\\x1f\\x7f]"));
    return text.contains(controlTextRe);
}

bool hasWhitespace(const QString &text) {
    for (const QChar ch : text) {
        if (ch.isSpace()) {
            return true;
        }
    }
    return false;
}

QString valueToText(const QJsonValue &value) {
    if (value.isUndefined() || value.isNull()) {
        return {};
    }
    if (value.isString()) {
        return value.toString();
    }
    if (value.isBool()) {
        return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    }
    if (value.isDouble()) {
        return QString::number(value.toDouble(), 'g', 15);
    }
    if (value.isObject()) {
        return QString::fromUtf8(QJsonDocument(value.toObject()).toJson(QJsonDocument::Compact));
    }
    if (value.isArray()) {
        return QString::fromUtf8(QJsonDocument(value.toArray()).toJson(QJsonDocument::Compact));
    }
    return {};
}

bool finiteFloat(const QJsonValue &value, double *out) {
    if (!out || value.isBool()) {
        return false;
    }
    bool ok = false;
    double number = 0.0;
    if (value.isDouble()) {
        number = value.toDouble();
        ok = true;
    } else if (value.isString()) {
        number = value.toString().trimmed().toDouble(&ok);
    } else {
        number = valueToText(value).trimmed().toDouble(&ok);
    }
    if (!ok || !std::isfinite(number)) {
        return false;
    }
    *out = number;
    return true;
}

bool coerceLooseBool(const QJsonValue &value, bool defaultValue, bool *out) {
    if (!out) {
        return false;
    }
    if (value.isBool()) {
        *out = value.toBool();
        return true;
    }
    if (value.isUndefined() || value.isNull()) {
        *out = defaultValue;
        return true;
    }
    if (value.isString()) {
        const QString text = value.toString().trimmed().toLower();
        if (text == QStringLiteral("1") || text == QStringLiteral("true") || text == QStringLiteral("yes") || text == QStringLiteral("on")) {
            *out = true;
            return true;
        }
        if (text == QStringLiteral("0") || text == QStringLiteral("false") || text == QStringLiteral("no") || text == QStringLiteral("off")) {
            *out = false;
            return true;
        }
        if (text.isEmpty() || text == QStringLiteral("none") || text == QStringLiteral("null")) {
            *out = defaultValue;
            return true;
        }
        return false;
    }
    double number = 0.0;
    if (finiteFloat(value, &number) && (number == 0.0 || number == 1.0)) {
        *out = number == 1.0;
        return true;
    }
    return false;
}

QString stringValue(const QJsonValue &value, bool allowEmpty = false) {
    const QString text = valueToText(value).trimmed();
    if (!allowEmpty && text.isEmpty()) {
        return {};
    }
    if (hasControlText(text)) {
        return {};
    }
    return text;
}

QString formatAmount(double value) {
    if (std::floor(value) == value) {
        return QString::number(static_cast<qint64>(value));
    }
    QString text = QString::number(value, 'g', 15);
    while (text.contains(QLatin1Char('.')) && text.endsWith(QLatin1Char('0'))) {
        text.chop(1);
    }
    if (text.endsWith(QLatin1Char('.'))) {
        text.chop(1);
    }
    return text;
}

QString normalizeInterval(const QJsonValue &value) {
    const QString raw = valueToText(value).trimmed();
    if (raw.isEmpty()) {
        return {};
    }
    static const QRegularExpression intervalRe(QStringLiteral("^\\s*(\\d+(?:\\.\\d+)?)\\s*([A-Za-z]*)\\s*$"));
    const QRegularExpressionMatch match = intervalRe.match(raw);
    if (!match.hasMatch()) {
        return {};
    }
    bool ok = false;
    const double amount = match.captured(1).toDouble(&ok);
    if (!ok || !std::isfinite(amount) || amount <= 0.0) {
        return {};
    }
    const QString suffix = match.captured(2).trimmed();
    QString unit;
    const QString lowerSuffix = suffix.toLower();
    if (suffix == QStringLiteral("M")
        || lowerSuffix == QStringLiteral("mo")
        || lowerSuffix == QStringLiteral("mon")
        || lowerSuffix == QStringLiteral("mons")
        || lowerSuffix == QStringLiteral("month")
        || lowerSuffix == QStringLiteral("months")) {
        unit = QStringLiteral("mo");
    } else if (lowerSuffix.isEmpty() || lowerSuffix == QStringLiteral("m") || lowerSuffix == QStringLiteral("min")
               || lowerSuffix == QStringLiteral("mins") || lowerSuffix == QStringLiteral("minute") || lowerSuffix == QStringLiteral("minutes")) {
        unit = QStringLiteral("m");
    } else if (lowerSuffix == QStringLiteral("s") || lowerSuffix == QStringLiteral("sec") || lowerSuffix == QStringLiteral("secs")
               || lowerSuffix == QStringLiteral("second") || lowerSuffix == QStringLiteral("seconds")) {
        unit = QStringLiteral("s");
    } else if (lowerSuffix == QStringLiteral("h") || lowerSuffix == QStringLiteral("hr") || lowerSuffix == QStringLiteral("hrs")
               || lowerSuffix == QStringLiteral("hour") || lowerSuffix == QStringLiteral("hours")) {
        unit = QStringLiteral("h");
    } else if (lowerSuffix == QStringLiteral("d") || lowerSuffix == QStringLiteral("day") || lowerSuffix == QStringLiteral("days")) {
        unit = QStringLiteral("d");
    } else if (lowerSuffix == QStringLiteral("w") || lowerSuffix == QStringLiteral("wk") || lowerSuffix == QStringLiteral("wks")
               || lowerSuffix == QStringLiteral("week") || lowerSuffix == QStringLiteral("weeks")) {
        unit = QStringLiteral("w");
    } else if (lowerSuffix == QStringLiteral("y") || lowerSuffix == QStringLiteral("yr") || lowerSuffix == QStringLiteral("yrs")
               || lowerSuffix == QStringLiteral("year") || lowerSuffix == QStringLiteral("years")) {
        unit = QStringLiteral("y");
    } else {
        return {};
    }
    return formatAmount(amount) + unit;
}

QString choiceValue(
    const QJsonValue &value,
    const QVector<QPair<QString, QString>> &choices) {
    const QString text = stringValue(value);
    if (text.isEmpty()) {
        return {};
    }
    const QString key = text.trimmed().toLower();
    for (const auto &choice : choices) {
        if (choice.first == key) {
            return choice.second;
        }
    }
    return {};
}

QString allowedChoiceText(const QVector<QPair<QString, QString>> &choices) {
    QSet<QString> values;
    for (const auto &choice : choices) {
        values.insert(choice.second);
    }
    QStringList out = values.values();
    out.sort();
    return out.join(QStringLiteral(", "));
}

const QVector<QPair<QString, QString>> &accountTypeChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("spot"), QStringLiteral("Spot")},
        {QStringLiteral("futures"), QStringLiteral("Futures")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &marginModeChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("isolated"), QStringLiteral("Isolated")},
        {QStringLiteral("cross"), QStringLiteral("Cross")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &positionModeChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("hedge"), QStringLiteral("Hedge")},
        {QStringLiteral("one-way"), QStringLiteral("One-way")},
        {QStringLiteral("oneway"), QStringLiteral("One-way")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &assetsModeChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("single-asset"), QStringLiteral("Single-Asset")},
        {QStringLiteral("single-asset mode"), QStringLiteral("Single-Asset")},
        {QStringLiteral("multi-assets"), QStringLiteral("Multi-Assets")},
        {QStringLiteral("multi-asset"), QStringLiteral("Multi-Assets")},
        {QStringLiteral("multi-assets mode"), QStringLiteral("Multi-Assets")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &accountModeChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("classic trading"), QStringLiteral("Classic Trading")},
        {QStringLiteral("portfolio margin"), QStringLiteral("Portfolio Margin")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &sideChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("both"), QStringLiteral("BOTH")},
        {QStringLiteral("buy"), QStringLiteral("BUY")},
        {QStringLiteral("sell"), QStringLiteral("SELL")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &orderTypeChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("market"), QStringLiteral("MARKET")},
        {QStringLiteral("limit"), QStringLiteral("LIMIT")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &timeInForceChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("gtc"), QStringLiteral("GTC")},
        {QStringLiteral("ioc"), QStringLiteral("IOC")},
        {QStringLiteral("fok"), QStringLiteral("FOK")},
        {QStringLiteral("gtd"), QStringLiteral("GTD")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &logicChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("and"), QStringLiteral("AND")},
        {QStringLiteral("or"), QStringLiteral("OR")},
        {QStringLiteral("separate"), QStringLiteral("SEPARATE")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &scanScopeChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("selected"), QStringLiteral("selected")},
        {QStringLiteral("top_n"), QStringLiteral("top_n")},
        {QStringLiteral("top-n"), QStringLiteral("top_n")},
        {QStringLiteral("all_loaded"), QStringLiteral("all_loaded")},
        {QStringLiteral("all-loaded"), QStringLiteral("all_loaded")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &optimizerModeChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("current"), QStringLiteral("current")},
        {QStringLiteral("single"), QStringLiteral("single")},
        {QStringLiteral("pairs"), QStringLiteral("pairs")},
        {QStringLiteral("combinations"), QStringLiteral("combinations")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &optimizerMetricChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("roi_percent"), QStringLiteral("roi_percent")},
        {QStringLiteral("roi-percent"), QStringLiteral("roi_percent")},
        {QStringLiteral("roi_percent_mdd"), QStringLiteral("roi_percent_mdd")},
        {QStringLiteral("roi-percent-mdd"), QStringLiteral("roi_percent_mdd")},
        {QStringLiteral("roi_drawdown"), QStringLiteral("roi_drawdown")},
        {QStringLiteral("roi-drawdown"), QStringLiteral("roi_drawdown")},
        {QStringLiteral("roi_value"), QStringLiteral("roi_value")},
        {QStringLiteral("roi-value"), QStringLiteral("roi_value")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &backtestExecutionBackendChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("desktop"), QStringLiteral("local")},
        {QStringLiteral("desktop-local"), QStringLiteral("local")},
        {QStringLiteral("local"), QStringLiteral("local")},
        {QStringLiteral("remote"), QStringLiteral("service")},
        {QStringLiteral("service"), QStringLiteral("service")},
        {QStringLiteral("service-api"), QStringLiteral("service")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &chartViewModeChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("tradingview"), QStringLiteral("tradingview")},
        {QStringLiteral("original"), QStringLiteral("original")},
        {QStringLiteral("lightweight"), QStringLiteral("lightweight")},
        {QStringLiteral("tradingview lightweight"), QStringLiteral("lightweight")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &llmProviderChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("alibaba"), QStringLiteral("qwen")},
        {QStringLiteral("alibaba-qwen"), QStringLiteral("qwen")},
        {QStringLiteral("anthropic"), QStringLiteral("anthropic")},
        {QStringLiteral("anthropic-claude"), QStringLiteral("anthropic")},
        {QStringLiteral("chatgpt"), QStringLiteral("openai")},
        {QStringLiteral("claude"), QStringLiteral("anthropic")},
        {QStringLiteral("custom"), QStringLiteral("local")},
        {QStringLiteral("dashscope"), QStringLiteral("qwen")},
        {QStringLiteral("deepseek"), QStringLiteral("deepseek")},
        {QStringLiteral("gemini"), QStringLiteral("gemini")},
        {QStringLiteral("google"), QStringLiteral("gemini")},
        {QStringLiteral("google-gemini"), QStringLiteral("gemini")},
        {QStringLiteral("grok"), QStringLiteral("grok")},
        {QStringLiteral("local"), QStringLiteral("local")},
        {QStringLiteral("local-openai"), QStringLiteral("local")},
        {QStringLiteral("local-openai-compatible"), QStringLiteral("local")},
        {QStringLiteral("ollama"), QStringLiteral("local")},
        {QStringLiteral("openai"), QStringLiteral("openai")},
        {QStringLiteral("openai-chatgpt"), QStringLiteral("openai")},
        {QStringLiteral("qwen"), QStringLiteral("qwen")},
        {QStringLiteral("xai"), QStringLiteral("grok")},
        {QStringLiteral("xai-grok"), QStringLiteral("grok")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &llmUseForChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("advisory"), QStringLiteral("advisory")},
        {QStringLiteral("backtest_explanation"), QStringLiteral("backtest_explanation")},
        {QStringLiteral("risk_review"), QStringLiteral("risk_review")},
        {QStringLiteral("signal_confirmation"), QStringLiteral("signal_confirmation")},
    };
    return choices;
}

const QVector<QPair<QString, QString>> &llmReasoningEffortChoices() {
    static const QVector<QPair<QString, QString>> choices{
        {QStringLiteral("default"), QStringLiteral("default")},
        {QStringLiteral("disabled"), QStringLiteral("disabled")},
        {QStringLiteral("enabled"), QStringLiteral("enabled")},
        {QStringLiteral("extra-high"), QStringLiteral("xhigh")},
        {QStringLiteral("extra_high"), QStringLiteral("xhigh")},
        {QStringLiteral("high"), QStringLiteral("high")},
        {QStringLiteral("low"), QStringLiteral("low")},
        {QStringLiteral("max"), QStringLiteral("max")},
        {QStringLiteral("medium"), QStringLiteral("medium")},
        {QStringLiteral("minimal"), QStringLiteral("minimal")},
        {QStringLiteral("none"), QStringLiteral("none")},
        {QStringLiteral("xhigh"), QStringLiteral("xhigh")},
    };
    return choices;
}

const QStringList &runtimeAllowedKeys() {
    static const QStringList keys{
        QStringLiteral("account_mode"), QStringLiteral("account_type"), QStringLiteral("add_only"),
        QStringLiteral("allow_close_ignoring_hold"), QStringLiteral("allow_indicator_close_without_signal"),
        QStringLiteral("allow_multi_indicator_close"), QStringLiteral("allow_opposite_positions"),
        QStringLiteral("api_key"), QStringLiteral("api_secret"), QStringLiteral("assets_mode"),
        QStringLiteral("auto_bump_percent_multiplier"), QStringLiteral("auto_flip_on_close"),
        QStringLiteral("backtest"), QStringLiteral("backtest_symbol_interval_pairs"), QStringLiteral("chart"),
        QStringLiteral("close_on_exit"), QStringLiteral("code_language"), QStringLiteral("connector_backend"),
        QStringLiteral("connector_order_block_circuit_breaker_enabled"), QStringLiteral("connector_order_block_pause_threshold"),
        QStringLiteral("connector_order_block_window_seconds"), QStringLiteral("connector_order_circuit_incident_log_backup_count"),
        QStringLiteral("connector_order_circuit_incident_log_max_bytes"), QStringLiteral("connector_order_circuit_incident_log_path"),
        QStringLiteral("design"), QStringLiteral("futures_flat_purge_grace_seconds"), QStringLiteral("futures_flat_purge_miss_threshold"),
        QStringLiteral("gtd_minutes"), QStringLiteral("hedge_preserve_opposites"), QStringLiteral("indicator_flip_confirmation_bars"),
        QStringLiteral("indicator_flip_cooldown_bars"), QStringLiteral("indicator_flip_cooldown_seconds"),
        QStringLiteral("indicator_min_position_hold_bars"), QStringLiteral("indicator_min_position_hold_seconds"),
        QStringLiteral("indicator_reentry_cooldown_bars"), QStringLiteral("indicator_reentry_cooldown_seconds"),
        QStringLiteral("indicator_reentry_requires_signal_reset"), QStringLiteral("indicator_source"),
        QStringLiteral("indicator_use_live_values"), QStringLiteral("indicators"), QStringLiteral("intervals"),
        QStringLiteral("lead_trader_enabled"), QStringLiteral("lead_trader_profile"), QStringLiteral("leverage"),
        QStringLiteral("live_trading_acknowledgement"), QStringLiteral("live_trading_enabled"),
        QStringLiteral("live_allow_auto_bump_to_min_order"), QStringLiteral("live_trading_max_leverage"),
        QStringLiteral("live_trading_max_position_pct"), QStringLiteral("live_trading_max_session_orders"),
        QStringLiteral("llm_allow_public_network"), QStringLiteral("llm_api_key"), QStringLiteral("llm_api_key_env"),
        QStringLiteral("llm_base_url"), QStringLiteral("llm_enabled"), QStringLiteral("llm_model"),
        QStringLiteral("llm_provider"), QStringLiteral("llm_reasoning_effort"), QStringLiteral("llm_use_for"),
        QStringLiteral("lookback"), QStringLiteral("loop_interval_override"), QStringLiteral("margin_mode"),
        QStringLiteral("max_auto_bump_percent"), QStringLiteral("mode"), QStringLiteral("operational_account_snapshot_stale_seconds"),
        QStringLiteral("operational_connector_snapshot_stale_seconds"), QStringLiteral("operational_execution_heartbeat_stale_seconds"),
        QStringLiteral("operational_live_order_gate_enabled"), QStringLiteral("operational_live_start_gate_enabled"),
        QStringLiteral("operational_portfolio_snapshot_stale_seconds"), QStringLiteral("order_audit_backup_count"),
        QStringLiteral("order_audit_enabled"), QStringLiteral("order_audit_log_path"), QStringLiteral("order_audit_max_bytes"),
        QStringLiteral("order_type"), QStringLiteral("position_mode"), QStringLiteral("position_pct"),
        QStringLiteral("positions_missing_autoclose"), QStringLiteral("positions_auto_resize_columns"),
        QStringLiteral("positions_auto_resize_rows"), QStringLiteral("positions_missing_grace_seconds"),
        QStringLiteral("positions_missing_threshold"), QStringLiteral("require_indicator_flip_signal"),
        QStringLiteral("runtime_symbol_interval_pairs"), QStringLiteral("selected_exchange"),
        QStringLiteral("selected_forex_broker"), QStringLiteral("selected_rust_framework"), QStringLiteral("side"),
        QStringLiteral("stop_loss"), QStringLiteral("strict_indicator_flip_enforcement"), QStringLiteral("symbols"),
        QStringLiteral("theme"), QStringLiteral("tif"),
    };
    return keys;
}

const QStringList &chartAllowedKeys() {
    static const QStringList keys{
        QStringLiteral("auto_follow"), QStringLiteral("interval"), QStringLiteral("market"),
        QStringLiteral("symbol"), QStringLiteral("view_mode"),
    };
    return keys;
}

const QStringList &backtestAllowedKeys() {
    static const QStringList keys{
        QStringLiteral("account_mode"), QStringLiteral("assets_mode"), QStringLiteral("capital"),
        QStringLiteral("connector_backend"), QStringLiteral("end_date"), QStringLiteral("execution_backend"),
        QStringLiteral("indicators"), QStringLiteral("intervals"), QStringLiteral("leverage"),
        QStringLiteral("logic"), QStringLiteral("margin_mode"), QStringLiteral("mdd_logic"),
        QStringLiteral("position_mode"), QStringLiteral("position_pct"), QStringLiteral("optimizer_combo_size"),
        QStringLiteral("optimizer_metric"), QStringLiteral("optimizer_min_trades"), QStringLiteral("optimizer_mode"),
        QStringLiteral("scan_auto_apply"), QStringLiteral("scan_mdd_limit"), QStringLiteral("scan_scope"),
        QStringLiteral("scan_top_n"), QStringLiteral("side"), QStringLiteral("start_date"),
        QStringLiteral("stop_loss"), QStringLiteral("symbol_source"), QStringLiteral("symbols"),
        QStringLiteral("template"),
    };
    return keys;
}

void validateAllowedKeys(
    const QJsonObject &cfg,
    const QStringList &allowedKeys,
    QJsonArray *issues,
    const QString &prefix = {}) {
    QStringList keys = cfg.keys();
    keys.sort();
    for (const QString &key : keys) {
        if (!allowedKeys.contains(key)) {
            addValidationIssue(issues, issueField(prefix, key), QStringLiteral("is not a supported config key"));
        }
    }
}

void validateText(QJsonObject *cfg, const QString &key, QJsonArray *issues, const QString &prefix = {}, bool allowEmpty = false) {
    if (!cfg || !cfg->contains(key)) {
        return;
    }
    const QString value = valueToText(cfg->value(key)).trimmed();
    if (value.isEmpty() && !allowEmpty) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be a non-empty text value"));
        return;
    }
    if (hasControlText(value)) {
        addValidationIssue(
            issues,
            issueField(prefix, key),
            allowEmpty ? QStringLiteral("must be text without control characters") : QStringLiteral("must be a non-empty text value"));
        return;
    }
    cfg->insert(key, value);
}

void validateNullableText(QJsonObject *cfg, const QString &key, QJsonArray *issues, const QString &prefix = {}, bool allowEmpty = false) {
    if (!cfg || !cfg->contains(key)) {
        return;
    }
    const QJsonValue value = cfg->value(key);
    if (value.isNull() || value.isUndefined()) {
        return;
    }
    const QString text = valueToText(value).trimmed();
    if (text.isEmpty() && !allowEmpty) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be a non-empty text value"));
        return;
    }
    if (hasControlText(text)) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be text without control characters"));
        return;
    }
    cfg->insert(key, text);
}

void validateDateTimeText(QJsonObject *cfg, const QString &key, QJsonArray *issues, const QString &prefix = {}) {
    if (!cfg || !cfg->contains(key)) {
        return;
    }
    const QJsonValue value = cfg->value(key);
    if (value.isNull() || value.isUndefined()) {
        return;
    }
    const QString text = valueToText(value).trimmed();
    if (text.isEmpty()) {
        cfg->insert(key, QString());
        return;
    }
    if (hasControlText(text)) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be text without control characters"));
        return;
    }
    const QString candidate = text.endsWith(QLatin1Char('Z')) ? text.left(text.size() - 1) + QStringLiteral("+00:00") : text;
    const bool valid = QDateTime::fromString(candidate, Qt::ISODate).isValid()
        || QDateTime::fromString(text, QStringLiteral("yyyy-MM-dd HH:mm:ss")).isValid()
        || QDate::fromString(text, QStringLiteral("yyyy-MM-dd")).isValid();
    if (!valid) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be an ISO date or datetime"));
        return;
    }
    cfg->insert(key, text);
}

void validateChoice(
    QJsonObject *cfg,
    const QString &key,
    const QVector<QPair<QString, QString>> &choices,
    QJsonArray *issues,
    const QString &prefix = {}) {
    if (!cfg || !cfg->contains(key)) {
        return;
    }
    const QString normalized = choiceValue(cfg->value(key), choices);
    if (normalized.isEmpty()) {
        addValidationIssue(
            issues,
            issueField(prefix, key),
            QStringLiteral("must be one of: %1").arg(allowedChoiceText(choices)));
        return;
    }
    cfg->insert(key, normalized);
}

void validateIntRange(
    QJsonObject *cfg,
    const QString &key,
    QJsonArray *issues,
    int minValue,
    int maxValue,
    const QString &prefix = {}) {
    if (!cfg || !cfg->contains(key)) {
        return;
    }
    double number = 0.0;
    if (!finiteFloat(cfg->value(key), &number) || std::floor(number) != number) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be an integer"));
        return;
    }
    const int integer = static_cast<int>(number);
    if (integer < minValue || integer > maxValue) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be between %1 and %2").arg(minValue).arg(maxValue));
        return;
    }
    cfg->insert(key, integer);
}

void validateFloatRange(
    QJsonObject *cfg,
    const QString &key,
    QJsonArray *issues,
    double minValue,
    double maxValue,
    const QString &prefix = {},
    bool exclusiveMin = false) {
    if (!cfg || !cfg->contains(key)) {
        return;
    }
    double number = 0.0;
    const bool minOk = finiteFloat(cfg->value(key), &number) && (exclusiveMin ? number > minValue : number >= minValue);
    if (!minOk || number > maxValue) {
        addValidationIssue(
            issues,
            issueField(prefix, key),
            QStringLiteral("must be %1 %2 and <= %3")
                .arg(exclusiveMin ? QStringLiteral(">") : QStringLiteral(">="))
                .arg(minValue, 0, 'g', 15)
                .arg(maxValue, 0, 'g', 15));
        return;
    }
    cfg->insert(key, number);
}

void validateBool(QJsonObject *cfg, const QString &key, QJsonArray *issues, const QString &prefix = {}, bool defaultValue = false) {
    if (!cfg || !cfg->contains(key)) {
        return;
    }
    bool out = false;
    if (!coerceLooseBool(cfg->value(key), defaultValue, &out)) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be a boolean"));
        return;
    }
    cfg->insert(key, out);
}

QJsonObject normalizedStopLossObject(const QJsonValue &value) {
    QJsonObject raw = value.isObject() ? value.toObject() : QJsonObject{};
    const QString rawMode = valueToText(raw.value(QStringLiteral("mode"))).trimmed().toLower();
    QString mode = rawMode;
    if (mode != QStringLiteral("usdt") && mode != QStringLiteral("percent") && mode != QStringLiteral("both")) {
        mode = QStringLiteral("usdt");
    }
    const QString rawScope = valueToText(raw.value(QStringLiteral("scope"))).trimmed().toLower();
    QString scope = rawScope;
    if (scope != QStringLiteral("per_trade") && scope != QStringLiteral("cumulative") && scope != QStringLiteral("entire_account")) {
        scope = QStringLiteral("per_trade");
    }
    bool enabled = false;
    coerceLooseBool(raw.value(QStringLiteral("enabled")), false, &enabled);
    double usdt = 0.0;
    if (!finiteFloat(raw.value(QStringLiteral("usdt")), &usdt) || usdt < 0.0) {
        usdt = 0.0;
    }
    double percent = 0.0;
    if (!finiteFloat(raw.value(QStringLiteral("percent")), &percent) || percent < 0.0) {
        percent = 0.0;
    }
    return QJsonObject{
        {QStringLiteral("enabled"), enabled},
        {QStringLiteral("mode"), mode},
        {QStringLiteral("usdt"), usdt},
        {QStringLiteral("percent"), percent},
        {QStringLiteral("scope"), scope},
    };
}

void validateStopLoss(QJsonObject *cfg, const QString &key, QJsonArray *issues, const QString &prefix = {}) {
    if (!cfg || !cfg->contains(key)) {
        return;
    }
    const QJsonValue value = cfg->value(key);
    if (!value.isNull() && !value.isUndefined() && !value.isObject()) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be an object"));
        return;
    }
    cfg->insert(key, normalizedStopLossObject(value));
}

void validateSymbolList(
    QJsonObject *cfg,
    const QString &key,
    QJsonArray *issues,
    const QString &prefix = {},
    bool requireNonEmpty = true) {
    if (!cfg || !cfg->contains(key)) {
        return;
    }
    QJsonArray values;
    const QJsonValue rawValue = cfg->value(key);
    if (rawValue.isString()) {
        values.append(rawValue);
    } else if (rawValue.isArray()) {
        values = rawValue.toArray();
    } else {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be a list of symbols"));
        return;
    }

    QSet<QString> seen;
    QJsonArray symbols;
    for (const QJsonValue &item : values) {
        const QString symbol = stringValue(item).toUpper();
        if (symbol.isEmpty() || hasWhitespace(symbol)) {
            addValidationIssue(issues, issueField(prefix, key), QStringLiteral("contains an invalid symbol"));
            continue;
        }
        if (!seen.contains(symbol)) {
            seen.insert(symbol);
            symbols.append(symbol);
        }
    }
    if (requireNonEmpty && symbols.isEmpty()) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must contain at least one symbol"));
        return;
    }
    cfg->insert(key, symbols);
}

void validateIntervalList(
    QJsonObject *cfg,
    const QString &key,
    QJsonArray *issues,
    const QString &prefix = {},
    bool requireNonEmpty = true) {
    if (!cfg || !cfg->contains(key)) {
        return;
    }
    QJsonArray values;
    const QJsonValue rawValue = cfg->value(key);
    if (rawValue.isString()) {
        values.append(rawValue);
    } else if (rawValue.isArray()) {
        values = rawValue.toArray();
    } else {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be a list of intervals"));
        return;
    }

    QSet<QString> seen;
    QJsonArray intervals;
    for (const QJsonValue &item : values) {
        const QString interval = normalizeInterval(item);
        if (interval.isEmpty()) {
            addValidationIssue(issues, issueField(prefix, key), QStringLiteral("contains an invalid interval"));
            continue;
        }
        if (!seen.contains(interval)) {
            seen.insert(interval);
            intervals.append(interval);
        }
    }
    if (requireNonEmpty && intervals.isEmpty()) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must contain at least one interval"));
        return;
    }
    cfg->insert(key, intervals);
}

void validateMapping(QJsonObject *cfg, const QString &key, QJsonArray *issues, const QString &prefix = {}) {
    if (cfg && cfg->contains(key) && !cfg->value(key).isObject()) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be an object"));
    }
}

void validatePairList(QJsonObject *cfg, const QString &key, QJsonArray *issues, const QString &prefix = {}) {
    if (!cfg || !cfg->contains(key)) {
        return;
    }
    const QJsonValue rawValue = cfg->value(key);
    if (rawValue.isNull() || rawValue.isUndefined() || (rawValue.isString() && rawValue.toString().trimmed().isEmpty())) {
        cfg->insert(key, QJsonArray{});
        return;
    }
    if (!rawValue.isArray()) {
        addValidationIssue(issues, issueField(prefix, key), QStringLiteral("must be a list of symbol/interval objects"));
        return;
    }
    QJsonArray normalized;
    const QJsonArray entries = rawValue.toArray();
    for (int index = 0; index < entries.size(); ++index) {
        const QString entryField = QStringLiteral("%1[%2]").arg(issueField(prefix, key)).arg(index);
        const QJsonValue rawEntry = entries.at(index);
        if (!rawEntry.isObject()) {
            addValidationIssue(issues, entryField, QStringLiteral("must be an object"));
            continue;
        }
        QJsonObject entry = rawEntry.toObject();
        const QString symbol = stringValue(entry.value(QStringLiteral("symbol"))).toUpper();
        const QString interval = normalizeInterval(entry.value(QStringLiteral("interval")));
        if (symbol.isEmpty() || hasWhitespace(symbol)) {
            addValidationIssue(issues, entryField + QStringLiteral(".symbol"), QStringLiteral("must be a non-empty symbol"));
            continue;
        }
        if (interval.isEmpty()) {
            addValidationIssue(issues, entryField + QStringLiteral(".interval"), QStringLiteral("must be a valid interval"));
            continue;
        }
        entry.insert(QStringLiteral("symbol"), symbol);
        entry.insert(QStringLiteral("interval"), interval);
        if (entry.contains(QStringLiteral("strategy_controls"))) {
            const QJsonValue controlsValue = entry.value(QStringLiteral("strategy_controls"));
            if (controlsValue.isObject()) {
                QJsonObject controls = controlsValue.toObject();
                validateChoice(&controls, QStringLiteral("side"), sideChoices(), issues, entryField + QStringLiteral(".strategy_controls"));
                validateIntRange(&controls, QStringLiteral("leverage"), issues, 1, 125, entryField + QStringLiteral(".strategy_controls"));
                if (controls.contains(QStringLiteral("loop_interval_override")) && !valueToText(controls.value(QStringLiteral("loop_interval_override"))).trimmed().isEmpty()) {
                    const QString loopInterval = normalizeInterval(controls.value(QStringLiteral("loop_interval_override")));
                    if (loopInterval.isEmpty()) {
                        addValidationIssue(issues, entryField + QStringLiteral(".strategy_controls.loop_interval_override"), QStringLiteral("must be a valid interval"));
                    } else {
                        controls.insert(QStringLiteral("loop_interval_override"), loopInterval);
                    }
                }
                validateStopLoss(&controls, QStringLiteral("stop_loss"), issues, entryField + QStringLiteral(".strategy_controls"));
                entry.insert(QStringLiteral("strategy_controls"), controls);
            } else if (!controlsValue.isNull() && !controlsValue.isUndefined()) {
                addValidationIssue(issues, entryField + QStringLiteral(".strategy_controls"), QStringLiteral("must be an object"));
            }
        }
        normalized.append(entry);
    }
    cfg->insert(key, normalized);
}

void validateChartConfig(QJsonObject *cfg, QJsonArray *issues) {
    if (!cfg || !cfg->contains(QStringLiteral("chart"))) {
        return;
    }
    const QJsonValue value = cfg->value(QStringLiteral("chart"));
    if (!value.isObject()) {
        addValidationIssue(issues, QStringLiteral("chart"), QStringLiteral("must be an object"));
        return;
    }
    QJsonObject chart = value.toObject();
    validateAllowedKeys(chart, chartAllowedKeys(), issues, QStringLiteral("chart"));
    validateChoice(&chart, QStringLiteral("market"), accountTypeChoices(), issues, QStringLiteral("chart"));
    validateChoice(&chart, QStringLiteral("view_mode"), chartViewModeChoices(), issues, QStringLiteral("chart"));
    validateBool(&chart, QStringLiteral("auto_follow"), issues, QStringLiteral("chart"), true);
    if (chart.contains(QStringLiteral("symbol"))) {
        const QString symbol = stringValue(chart.value(QStringLiteral("symbol"))).toUpper();
        if (symbol.isEmpty() || hasWhitespace(symbol)) {
            addValidationIssue(issues, QStringLiteral("chart.symbol"), QStringLiteral("must be a non-empty symbol"));
        } else {
            chart.insert(QStringLiteral("symbol"), symbol);
        }
    }
    if (chart.contains(QStringLiteral("interval"))) {
        const QString interval = normalizeInterval(chart.value(QStringLiteral("interval")));
        if (interval.isEmpty()) {
            addValidationIssue(issues, QStringLiteral("chart.interval"), QStringLiteral("must be a valid interval"));
        } else {
            chart.insert(QStringLiteral("interval"), interval);
        }
    }
    cfg->insert(QStringLiteral("chart"), chart);
}

void validateBacktestConfig(QJsonObject *cfg, QJsonArray *issues) {
    if (!cfg || !cfg->contains(QStringLiteral("backtest"))) {
        return;
    }
    const QJsonValue value = cfg->value(QStringLiteral("backtest"));
    if (!value.isObject()) {
        addValidationIssue(issues, QStringLiteral("backtest"), QStringLiteral("must be an object"));
        return;
    }
    QJsonObject backtest = value.toObject();
    validateAllowedKeys(backtest, backtestAllowedKeys(), issues, QStringLiteral("backtest"));
    validateSymbolList(&backtest, QStringLiteral("symbols"), issues, QStringLiteral("backtest"));
    validateIntervalList(&backtest, QStringLiteral("intervals"), issues, QStringLiteral("backtest"));
    validateFloatRange(&backtest, QStringLiteral("capital"), issues, 0.0, 1'000'000'000'000.0, QStringLiteral("backtest"), true);
    validateChoice(&backtest, QStringLiteral("execution_backend"), backtestExecutionBackendChoices(), issues, QStringLiteral("backtest"));
    validateChoice(&backtest, QStringLiteral("logic"), logicChoices(), issues, QStringLiteral("backtest"));
    validateText(&backtest, QStringLiteral("symbol_source"), issues, QStringLiteral("backtest"));
    validateDateTimeText(&backtest, QStringLiteral("start_date"), issues, QStringLiteral("backtest"));
    validateDateTimeText(&backtest, QStringLiteral("end_date"), issues, QStringLiteral("backtest"));
    validateFloatRange(&backtest, QStringLiteral("position_pct"), issues, 0.0, 100.0, QStringLiteral("backtest"), true);
    validateChoice(&backtest, QStringLiteral("side"), sideChoices(), issues, QStringLiteral("backtest"));
    validateChoice(&backtest, QStringLiteral("margin_mode"), marginModeChoices(), issues, QStringLiteral("backtest"));
    validateChoice(&backtest, QStringLiteral("position_mode"), positionModeChoices(), issues, QStringLiteral("backtest"));
    validateChoice(&backtest, QStringLiteral("assets_mode"), assetsModeChoices(), issues, QStringLiteral("backtest"));
    validateChoice(&backtest, QStringLiteral("account_mode"), accountModeChoices(), issues, QStringLiteral("backtest"));
    validateText(&backtest, QStringLiteral("connector_backend"), issues, QStringLiteral("backtest"));
    validateIntRange(&backtest, QStringLiteral("leverage"), issues, 1, 125, QStringLiteral("backtest"));
    if (backtest.contains(QStringLiteral("mdd_logic"))) {
        static const QVector<QPair<QString, QString>> mddChoices{
            {QStringLiteral("per_trade"), QStringLiteral("per_trade")},
            {QStringLiteral("cumulative"), QStringLiteral("cumulative")},
            {QStringLiteral("entire_account"), QStringLiteral("entire_account")},
        };
        validateChoice(&backtest, QStringLiteral("mdd_logic"), mddChoices, issues, QStringLiteral("backtest"));
    }
    validateChoice(&backtest, QStringLiteral("scan_scope"), scanScopeChoices(), issues, QStringLiteral("backtest"));
    validateIntRange(&backtest, QStringLiteral("scan_top_n"), issues, 1, 10'000, QStringLiteral("backtest"));
    validateFloatRange(&backtest, QStringLiteral("scan_mdd_limit"), issues, 0.0, 100.0, QStringLiteral("backtest"));
    validateBool(&backtest, QStringLiteral("scan_auto_apply"), issues, QStringLiteral("backtest"));
    validateChoice(&backtest, QStringLiteral("optimizer_mode"), optimizerModeChoices(), issues, QStringLiteral("backtest"));
    validateChoice(&backtest, QStringLiteral("optimizer_metric"), optimizerMetricChoices(), issues, QStringLiteral("backtest"));
    validateIntRange(&backtest, QStringLiteral("optimizer_combo_size"), issues, 1, 5, QStringLiteral("backtest"));
    validateIntRange(&backtest, QStringLiteral("optimizer_min_trades"), issues, 0, 1'000'000, QStringLiteral("backtest"));
    validateMapping(&backtest, QStringLiteral("template"), issues, QStringLiteral("backtest"));
    validateMapping(&backtest, QStringLiteral("indicators"), issues, QStringLiteral("backtest"));
    validateStopLoss(&backtest, QStringLiteral("stop_loss"), issues, QStringLiteral("backtest"));
    cfg->insert(QStringLiteral("backtest"), backtest);
}

} // namespace

namespace NativeConfigPersistence {

bool serviceConfigEnvFlag(const QString &value, bool defaultValue) {
    const QString text = value.trimmed().toLower();
    if (text.isEmpty()) {
        return defaultValue;
    }
    return text == QStringLiteral("1")
        || text == QStringLiteral("true")
        || text == QStringLiteral("yes")
        || text == QStringLiteral("on");
}

QString serviceConfigDefaultPath() {
    return QStringLiteral("~/.trading-bot/service-config.json");
}

QString resolveServiceConfigPath(const QString &path) {
    QString rawPath = path.trimmed();
    if (rawPath.isEmpty()) {
        rawPath = envValue(ServiceConfigEnvPath);
    }
    if (rawPath.isEmpty()) {
        rawPath = serviceConfigDefaultPath();
    }
    return absoluteCleanPath(rawPath);
}

QString serviceConfigSafeRoot() {
    return QFileInfo(resolveServiceConfigPath(serviceConfigDefaultPath())).absoluteDir().absolutePath();
}

QString ensureServiceConfigPathAllowed(const QString &path, bool allowUnsafePath) {
    const QString resolved = resolveServiceConfigPath(path);
    if (allowUnsafePath || serviceConfigEnvFlag(envValue(ServiceConfigAllowUnsafePathEnv), false)) {
        return resolved;
    }
    const QString safeRoot = serviceConfigSafeRoot();
    if (isRelativeTo(resolved, safeRoot)) {
        return resolved;
    }
    throw std::runtime_error(
        QStringLiteral(
            "Service config path %1 is outside the safe config directory %2. "
            "Use allow_unsafe_path=true or set %3=1 only for trusted local paths.")
            .arg(resolved, safeRoot, QString::fromLatin1(ServiceConfigAllowUnsafePathEnv))
            .toStdString());
}

bool isServiceConfigSecretKey(const QString &key) {
    QString text = key.trimmed().toLower().replace(QLatin1Char('-'), QLatin1Char('_'));
    if (text.endsWith(QStringLiteral("_env")) || text.endsWith(QStringLiteral("_env_var"))) {
        return false;
    }
    static const QStringList tokens = {
        QStringLiteral("api_key"),
        QStringLiteral("api_secret"),
        QStringLiteral("apikey"),
        QStringLiteral("api_token"),
        QStringLiteral("authorization"),
        QStringLiteral("bearer"),
        QStringLiteral("password"),
        QStringLiteral("secret"),
        QStringLiteral("signature"),
        QStringLiteral("token"),
    };
    for (const QString &token : tokens) {
        if (text.contains(token)) {
            return true;
        }
    }
    return false;
}

QStringList serviceConfigSecretFieldPaths(const QJsonValue &payload) {
    QSet<QString> paths;
    collectSecretFieldPaths(payload, {}, &paths);
    QStringList out = paths.values();
    out.sort();
    return out;
}

QJsonObject serviceConfigSecretMetadata(const QJsonObject &config) {
    const QStringList fields = serviceConfigSecretFieldPaths(config);
    return QJsonObject{
        {QStringLiteral("contains_secrets"), !fields.isEmpty()},
        {QStringLiteral("secret_fields"), toJsonArray(fields)},
        {QStringLiteral("secret_storage"), QString::fromLatin1(ServiceConfigSecretStorage)},
        {QStringLiteral("secret_storage_warning"),
         fields.isEmpty() ? QString() : QString::fromLatin1(ServiceConfigSecretStorageWarning)},
    };
}

QJsonValue withoutInlineServiceConfigSecretValues(const QJsonValue &payload) {
    return stripInlineSecrets(payload);
}

QString formatServiceConfigValidationIssues(const QJsonArray &issues) {
    if (issues.isEmpty()) {
        return QStringLiteral("Invalid config.");
    }
    QStringList parts;
    for (const QJsonValue &value : issues) {
        const QJsonObject issue = value.toObject();
        parts.append(QStringLiteral("%1: %2")
            .arg(issue.value(QStringLiteral("field")).toString(),
                 issue.value(QStringLiteral("message")).toString()));
    }
    return QStringLiteral("Invalid config: %1").arg(parts.join(QStringLiteral("; ")));
}

ServiceConfigValidationResult validateServiceRuntimeConfig(const QJsonObject &config) {
    ServiceConfigValidationResult result;
    QJsonObject cfg = config;
    QJsonArray issues;

    validateAllowedKeys(cfg, runtimeAllowedKeys(), &issues);
    validateText(&cfg, QStringLiteral("api_key"), &issues, {}, true);
    validateText(&cfg, QStringLiteral("api_secret"), &issues, {}, true);
    validateText(&cfg, QStringLiteral("mode"), &issues);
    validateChoice(&cfg, QStringLiteral("account_type"), accountTypeChoices(), &issues);
    validateChoice(&cfg, QStringLiteral("margin_mode"), marginModeChoices(), &issues);
    validateSymbolList(&cfg, QStringLiteral("symbols"), &issues);
    validateIntervalList(&cfg, QStringLiteral("intervals"), &issues);
    validateIntRange(&cfg, QStringLiteral("lookback"), &issues, 1, 1'000'000);
    validateIntRange(&cfg, QStringLiteral("leverage"), &issues, 1, 125);
    validateChoice(&cfg, QStringLiteral("tif"), timeInForceChoices(), &issues);
    validateIntRange(&cfg, QStringLiteral("gtd_minutes"), &issues, 1, 7 * 24 * 60);
    validateChoice(&cfg, QStringLiteral("position_mode"), positionModeChoices(), &issues);
    validateChoice(&cfg, QStringLiteral("assets_mode"), assetsModeChoices(), &issues);
    validateChoice(&cfg, QStringLiteral("account_mode"), accountModeChoices(), &issues);
    validateBool(&cfg, QStringLiteral("lead_trader_enabled"), &issues);
    validateNullableText(&cfg, QStringLiteral("lead_trader_profile"), &issues, {}, true);
    validateText(&cfg, QStringLiteral("loop_interval_override"), &issues, {}, true);
    if (cfg.contains(QStringLiteral("loop_interval_override"))
        && !cfg.value(QStringLiteral("loop_interval_override")).toString().trimmed().isEmpty()) {
        const QString loopInterval = normalizeInterval(cfg.value(QStringLiteral("loop_interval_override")));
        if (loopInterval.isEmpty()) {
            addValidationIssue(&issues, QStringLiteral("loop_interval_override"), QStringLiteral("must be a valid interval"));
        } else {
            cfg.insert(QStringLiteral("loop_interval_override"), loopInterval);
        }
    }
    validatePairList(&cfg, QStringLiteral("runtime_symbol_interval_pairs"), &issues);
    validatePairList(&cfg, QStringLiteral("backtest_symbol_interval_pairs"), &issues);
    validateChoice(&cfg, QStringLiteral("side"), sideChoices(), &issues);
    validateFloatRange(&cfg, QStringLiteral("position_pct"), &issues, 0.0, 100.0, {}, true);
    validateChoice(&cfg, QStringLiteral("order_type"), orderTypeChoices(), &issues);
    validateBool(&cfg, QStringLiteral("live_trading_enabled"), &issues);
    validateText(&cfg, QStringLiteral("live_trading_acknowledgement"), &issues, {}, true);
    validateBool(&cfg, QStringLiteral("live_allow_auto_bump_to_min_order"), &issues, {}, false);
    validateIntRange(&cfg, QStringLiteral("live_trading_max_leverage"), &issues, 1, 125);
    validateFloatRange(&cfg, QStringLiteral("live_trading_max_position_pct"), &issues, 0.0, 100.0, {}, true);
    validateIntRange(&cfg, QStringLiteral("live_trading_max_session_orders"), &issues, 1, 100'000);
    validateBool(&cfg, QStringLiteral("order_audit_enabled"), &issues, {}, true);
    validateBool(&cfg, QStringLiteral("positions_auto_resize_rows"), &issues, {}, true);
    validateBool(&cfg, QStringLiteral("positions_auto_resize_columns"), &issues, {}, true);
    validateText(&cfg, QStringLiteral("order_audit_log_path"), &issues, {}, true);
    validateIntRange(&cfg, QStringLiteral("order_audit_max_bytes"), &issues, 1, 1'000'000'000);
    validateIntRange(&cfg, QStringLiteral("order_audit_backup_count"), &issues, 0, 100);
    validateText(&cfg, QStringLiteral("connector_order_circuit_incident_log_path"), &issues, {}, true);
    validateIntRange(&cfg, QStringLiteral("connector_order_circuit_incident_log_max_bytes"), &issues, 1, 1'000'000'000);
    validateIntRange(&cfg, QStringLiteral("connector_order_circuit_incident_log_backup_count"), &issues, 0, 100);
    validateFloatRange(&cfg, QStringLiteral("operational_connector_snapshot_stale_seconds"), &issues, 1.0, 24.0 * 60.0 * 60.0);
    validateFloatRange(&cfg, QStringLiteral("operational_execution_heartbeat_stale_seconds"), &issues, 1.0, 24.0 * 60.0 * 60.0);
    validateFloatRange(&cfg, QStringLiteral("operational_account_snapshot_stale_seconds"), &issues, 1.0, 24.0 * 60.0 * 60.0);
    validateFloatRange(&cfg, QStringLiteral("operational_portfolio_snapshot_stale_seconds"), &issues, 1.0, 24.0 * 60.0 * 60.0);
    validateBool(&cfg, QStringLiteral("operational_live_start_gate_enabled"), &issues, {}, true);
    validateBool(&cfg, QStringLiteral("operational_live_order_gate_enabled"), &issues, {}, true);
    validateBool(&cfg, QStringLiteral("connector_order_block_circuit_breaker_enabled"), &issues, {}, true);
    validateIntRange(&cfg, QStringLiteral("connector_order_block_pause_threshold"), &issues, 1, 1'000'000);
    validateFloatRange(&cfg, QStringLiteral("connector_order_block_window_seconds"), &issues, 1.0, 24.0 * 60.0 * 60.0);

    for (const QString &key : {
             QStringLiteral("add_only"),
             QStringLiteral("indicator_use_live_values"),
             QStringLiteral("require_indicator_flip_signal"),
             QStringLiteral("strict_indicator_flip_enforcement"),
             QStringLiteral("indicator_reentry_requires_signal_reset"),
             QStringLiteral("auto_flip_on_close"),
             QStringLiteral("allow_close_ignoring_hold"),
             QStringLiteral("allow_multi_indicator_close"),
             QStringLiteral("allow_indicator_close_without_signal"),
             QStringLiteral("close_on_exit"),
             QStringLiteral("positions_missing_autoclose"),
             QStringLiteral("allow_opposite_positions"),
             QStringLiteral("hedge_preserve_opposites"),
         }) {
        validateBool(&cfg, key, &issues);
    }

    const QVector<QPair<QString, QPair<int, int>>> intRanges{
        {QStringLiteral("indicator_flip_cooldown_bars"), {0, 1'000'000}},
        {QStringLiteral("indicator_min_position_hold_bars"), {0, 1'000'000}},
        {QStringLiteral("indicator_reentry_cooldown_bars"), {0, 1'000'000}},
        {QStringLiteral("indicator_flip_confirmation_bars"), {1, 1'000'000}},
        {QStringLiteral("positions_missing_threshold"), {1, 1'000'000}},
        {QStringLiteral("futures_flat_purge_miss_threshold"), {1, 1'000'000}},
    };
    for (const auto &range : intRanges) {
        validateIntRange(&cfg, range.first, &issues, range.second.first, range.second.second);
    }

    const QVector<QPair<QString, QPair<double, double>>> floatRanges{
        {QStringLiteral("indicator_flip_cooldown_seconds"), {0.0, 365.0 * 24.0 * 60.0 * 60.0}},
        {QStringLiteral("indicator_min_position_hold_seconds"), {0.0, 365.0 * 24.0 * 60.0 * 60.0}},
        {QStringLiteral("indicator_reentry_cooldown_seconds"), {0.0, 365.0 * 24.0 * 60.0 * 60.0}},
        {QStringLiteral("positions_missing_grace_seconds"), {0.0, 365.0 * 24.0 * 60.0 * 60.0}},
        {QStringLiteral("futures_flat_purge_grace_seconds"), {0.0, 365.0 * 24.0 * 60.0 * 60.0}},
        {QStringLiteral("max_auto_bump_percent"), {0.0, 100.0}},
        {QStringLiteral("auto_bump_percent_multiplier"), {0.0, 1'000.0}},
    };
    for (const auto &range : floatRanges) {
        validateFloatRange(&cfg, range.first, &issues, range.second.first, range.second.second);
    }

    validateText(&cfg, QStringLiteral("connector_backend"), &issues);
    validateText(&cfg, QStringLiteral("indicator_source"), &issues);
    validateText(&cfg, QStringLiteral("code_language"), &issues);
    validateText(&cfg, QStringLiteral("theme"), &issues, {}, true);
    validateText(&cfg, QStringLiteral("design"), &issues, {}, true);
    validateText(&cfg, QStringLiteral("selected_rust_framework"), &issues, {}, true);
    validateText(&cfg, QStringLiteral("selected_exchange"), &issues);
    validateText(&cfg, QStringLiteral("selected_forex_broker"), &issues, {}, true);
    validateBool(&cfg, QStringLiteral("llm_enabled"), &issues);
    validateChoice(&cfg, QStringLiteral("llm_provider"), llmProviderChoices(), &issues);
    validateText(&cfg, QStringLiteral("llm_model"), &issues, {}, true);
    validateText(&cfg, QStringLiteral("llm_base_url"), &issues, {}, true);
    validateText(&cfg, QStringLiteral("llm_api_key"), &issues, {}, true);
    validateText(&cfg, QStringLiteral("llm_api_key_env"), &issues, {}, true);
    validateChoice(&cfg, QStringLiteral("llm_use_for"), llmUseForChoices(), &issues);
    validateBool(&cfg, QStringLiteral("llm_allow_public_network"), &issues);
    validateChoice(&cfg, QStringLiteral("llm_reasoning_effort"), llmReasoningEffortChoices(), &issues);
    validateStopLoss(&cfg, QStringLiteral("stop_loss"), &issues);
    validateMapping(&cfg, QStringLiteral("indicators"), &issues);
    validateChartConfig(&cfg, &issues);
    validateBacktestConfig(&cfg, &issues);

    result.config = cfg;
    result.issues = issues;
    result.ok = issues.isEmpty();
    result.error = result.ok ? QString() : formatServiceConfigValidationIssues(issues);
    return result;
}

QJsonObject buildServiceConfigPersistencePayload(
    const QJsonObject &config,
    const QDateTime &savedAt,
    bool allowInlineSecrets) {
    const QJsonObject secretMetadata = serviceConfigSecretMetadata(config);
    const bool containsSecrets = secretMetadata.value(QStringLiteral("contains_secrets")).toBool(false);
    const QJsonValue persistedConfig = (containsSecrets && !allowInlineSecrets)
        ? withoutInlineServiceConfigSecretValues(config)
        : QJsonValue(config);

    QJsonObject payload{
        {QStringLiteral("kind"), QString::fromLatin1(ServiceConfigFileKind)},
        {QStringLiteral("format_version"), ServiceConfigFormatVersion},
        {QStringLiteral("saved_at"), currentIso(savedAt)},
        {QStringLiteral("config"), persistedConfig},
        {QStringLiteral("inline_secrets_persisted"), containsSecrets && allowInlineSecrets},
    };
    for (auto it = secretMetadata.constBegin(); it != secretMetadata.constEnd(); ++it) {
        payload.insert(it.key(), it.value());
    }
    return payload;
}

ServiceConfigLoadResult coerceServiceConfigPersistencePayload(
    const QJsonValue &rawPayload,
    const QString &path) {
    ServiceConfigLoadResult result;
    if (!rawPayload.isObject()) {
        result.error = QStringLiteral("Service config file %1 must contain a JSON object.").arg(path);
        return result;
    }

    const QJsonObject raw = rawPayload.toObject();
    QJsonValue configPayload(raw);
    QJsonObject metadata{
        {QStringLiteral("kind"), QStringLiteral("legacy-config")},
        {QStringLiteral("format_version"), QJsonValue::Null},
        {QStringLiteral("saved_at"), QString()},
        {QStringLiteral("migrated_from_format_version"), QJsonValue::Null},
    };

    const bool looksLikeEnvelope = raw.contains(QStringLiteral("config"))
        && (raw.value(QStringLiteral("kind")).toString() == QString::fromLatin1(ServiceConfigFileKind)
            || raw.contains(QStringLiteral("format_version"))
            || raw.contains(QStringLiteral("saved_at")));

    if (looksLikeEnvelope) {
        int versionNumber = ServiceConfigFormatVersion;
        if (!parseFormatVersion(raw.value(QStringLiteral("format_version")), &versionNumber)) {
            result.error = QStringLiteral("Service config file %1 has an invalid format_version.").arg(path);
            return result;
        }
        if (versionNumber > ServiceConfigFormatVersion) {
            result.error = QStringLiteral("Service config file %1 uses unsupported format_version %2.")
                               .arg(path)
                               .arg(versionNumber);
            return result;
        }
        configPayload = raw.value(QStringLiteral("config"));
        metadata = QJsonObject{
            {QStringLiteral("kind"), raw.value(QStringLiteral("kind")).toString(QString::fromLatin1(ServiceConfigFileKind))},
            {QStringLiteral("format_version"), ServiceConfigFormatVersion},
            {QStringLiteral("migrated_from_format_version"),
             versionNumber < ServiceConfigFormatVersion ? QJsonValue(versionNumber) : QJsonValue(QJsonValue::Null)},
            {QStringLiteral("saved_at"), raw.value(QStringLiteral("saved_at")).toString()},
        };
    }

    if (!configPayload.isObject()) {
        result.error = QStringLiteral("Service config file %1 must contain a config object.").arg(path);
        return result;
    }

    const ServiceConfigValidationResult validation = validateServiceRuntimeConfig(configPayload.toObject());
    if (!validation.ok) {
        result.error = validation.error;
        result.metadata.insert(QStringLiteral("validation_issues"), validation.issues);
        return result;
    }

    result.ok = true;
    result.config = validation.config;
    result.metadata = metadata;
    return result;
}

ServiceConfigLoadResult loadServiceConfigFile(const QString &path) {
    const QString resolvedPath = resolveServiceConfigPath(path);
    QFile file(resolvedPath);
    ServiceConfigLoadResult result;
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        result.error = QStringLiteral("Service config file not found: %1").arg(resolvedPath);
        return result;
    }

    QJsonParseError parseError{};
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError) {
        result.error = QStringLiteral("Service config file %1 is invalid JSON: %2")
                           .arg(resolvedPath, parseError.errorString());
        return result;
    }

    result = coerceServiceConfigPersistencePayload(document.isObject() ? QJsonValue(document.object()) : QJsonValue(), resolvedPath);
    if (!result.ok) {
        return result;
    }
    result.metadata.insert(QStringLiteral("path"), resolvedPath);
    result.metadata.insert(QStringLiteral("exists"), true);
    result.metadata.insert(QStringLiteral("loaded_at"), currentIso());
    if (!result.metadata.contains(QStringLiteral("kind")) || result.metadata.value(QStringLiteral("kind")).toString().isEmpty()) {
        result.metadata.insert(QStringLiteral("kind"), QString::fromLatin1(ServiceConfigFileKind));
    }
    result.metadata.insert(QStringLiteral("format_version"), ServiceConfigFormatVersion);
    return result;
}

QJsonObject writeServiceConfigFile(
    const QJsonObject &config,
    const QString &path,
    bool allowUnsafePath,
    bool allowInlineSecrets,
    const QDateTime &savedAt) {
    const QString resolvedPath = ensureServiceConfigPathAllowed(path, allowUnsafePath);
    const ServiceConfigValidationResult validation = validateServiceRuntimeConfig(config);
    if (!validation.ok) {
        throw std::runtime_error(validation.error.toStdString());
    }
    const QJsonObject payload = buildServiceConfigPersistencePayload(validation.config, savedAt, allowInlineSecrets);

    const QFileInfo info(resolvedPath);
    QDir().mkpath(info.absolutePath());
    QSaveFile file(resolvedPath);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        throw std::runtime_error(QStringLiteral("Could not write service config file %1.").arg(resolvedPath).toStdString());
    }
    file.write(QJsonDocument(payload).toJson(QJsonDocument::Indented));
    file.write("\n");
    if (!file.commit()) {
        throw std::runtime_error(QStringLiteral("Could not commit service config file %1.").arg(resolvedPath).toStdString());
    }
    QFile::setPermissions(
        resolvedPath,
        QFileDevice::ReadOwner | QFileDevice::WriteOwner);

    QJsonObject metadata{
        {QStringLiteral("path"), resolvedPath},
        {QStringLiteral("exists"), true},
        {QStringLiteral("saved_at"), payload.value(QStringLiteral("saved_at")).toString()},
        {QStringLiteral("kind"), QString::fromLatin1(ServiceConfigFileKind)},
        {QStringLiteral("format_version"), ServiceConfigFormatVersion},
    };
    const QJsonObject secretMetadata = serviceConfigSecretMetadata(validation.config);
    for (auto it = secretMetadata.constBegin(); it != secretMetadata.constEnd(); ++it) {
        metadata.insert(it.key(), it.value());
    }
    metadata.insert(QStringLiteral("inline_secrets_persisted"), payload.value(QStringLiteral("inline_secrets_persisted")).toBool(false));
    return metadata;
}

QJsonObject serviceConfigFileStatus(const QString &path) {
    const QString resolvedPath = resolveServiceConfigPath(path);
    QFileInfo info(resolvedPath);
    QJsonObject secretMetadata;
    QString modifiedAt;
    if (info.isFile()) {
        modifiedAt = currentIso(info.lastModified().toUTC());
        QFile file(resolvedPath);
        if (file.open(QIODevice::ReadOnly | QIODevice::Text)) {
            QJsonParseError parseError{};
            const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &parseError);
            if (parseError.error == QJsonParseError::NoError && document.isObject()) {
                const QJsonObject raw = document.object();
                secretMetadata = QJsonObject{
                    {QStringLiteral("contains_secrets"), raw.value(QStringLiteral("contains_secrets")).toBool(false)},
                    {QStringLiteral("secret_fields"), raw.value(QStringLiteral("secret_fields")).toArray()},
                    {QStringLiteral("secret_storage"), raw.value(QStringLiteral("secret_storage")).toString()},
                    {QStringLiteral("secret_storage_warning"), raw.value(QStringLiteral("secret_storage_warning")).toString()},
                };
            }
        }
    }

    QJsonObject status{
        {QStringLiteral("path"), resolvedPath},
        {QStringLiteral("exists"), info.isFile()},
        {QStringLiteral("modified_at"), modifiedAt},
        {QStringLiteral("kind"), QString::fromLatin1(ServiceConfigFileKind)},
        {QStringLiteral("format_version"), ServiceConfigFormatVersion},
    };
    insertNonEmptySecretMetadata(&status, secretMetadata);
    return status;
}

QJsonObject buildServiceConfigPersistenceStatus(
    const QJsonObject &fileStatus,
    const ServiceConfigRuntimeState &runtimeState) {
    QJsonObject status = fileStatus;
    status.insert(QStringLiteral("loaded"), runtimeState.loaded || !runtimeState.lastLoadedAt.isEmpty());
    status.insert(QStringLiteral("dirty"), runtimeState.dirty);
    status.insert(QStringLiteral("last_loaded_at"), runtimeState.lastLoadedAt);
    status.insert(QStringLiteral("last_saved_at"), runtimeState.lastSavedAt);
    status.insert(QStringLiteral("migrated_from_format_version"), runtimeState.migratedFromFormatVersion);
    return status;
}

} // namespace NativeConfigPersistence
