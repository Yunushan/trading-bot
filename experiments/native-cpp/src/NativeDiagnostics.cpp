#include "NativeDiagnostics.h"

#include "NativeOrderSafety.h"

#include <algorithm>

namespace {

QString isoNow(const QDateTime &value) {
    const QDateTime stamp = value.isValid() ? value : QDateTime::currentDateTimeUtc();
    return stamp.toUTC().toString(Qt::ISODateWithMs);
}

QString normalizedSource(const QString &value, const QString &fallback) {
    const QString text = value.trimmed().isEmpty() ? fallback : value.trimmed();
    return NativeOrderSafety::redactText(text);
}

} // namespace

namespace NativeDiagnostics {

QJsonObject buildServiceLogEvent(
    const QString &message,
    const QString &source,
    const QString &level,
    int sequenceId,
    const QDateTime &generatedAt) {
    const QString normalizedLevel = level.trimmed().isEmpty()
        ? QStringLiteral("info")
        : level.trimmed().toLower();
    return {
        {QStringLiteral("sequence_id"), std::max(0, sequenceId)},
        {QStringLiteral("level"), normalizedLevel},
        {QStringLiteral("message"), NativeOrderSafety::redactText(message)},
        {QStringLiteral("source"), normalizedSource(source, QStringLiteral("service"))},
        {QStringLiteral("generated_at"), isoNow(generatedAt)},
    };
}

QJsonObject buildServiceTerminalCommandResult(
    bool accepted,
    const QString &command,
    const QString &output,
    const QString &source,
    int exitCode,
    const QDateTime &createdAt) {
    return {
        {QStringLiteral("accepted"), accepted},
        {QStringLiteral("command"), NativeOrderSafety::redactText(command.trimmed())},
        {QStringLiteral("exit_code"), exitCode},
        {QStringLiteral("output"), NativeOrderSafety::redactText(output)},
        {QStringLiteral("source"), normalizedSource(source, QStringLiteral("terminal"))},
        {QStringLiteral("created_at"), isoNow(createdAt)},
        {QStringLiteral("command_type"), QStringLiteral("service-command")},
    };
}

QString formatServiceLogLine(const QJsonObject &event) {
    const QString generatedAt = event.value(QStringLiteral("generated_at")).toString();
    const QString level = event.value(QStringLiteral("level")).toString(QStringLiteral("info")).toUpper();
    const QString source = event.value(QStringLiteral("source")).toString(QStringLiteral("service"));
    const QString message = event.value(QStringLiteral("message")).toString();
    return QStringLiteral("%1 [%2] %3: %4")
        .arg(generatedAt, level, source, message)
        .trimmed();
}

} // namespace NativeDiagnostics
