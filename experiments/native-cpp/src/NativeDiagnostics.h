#pragma once

#include <QDateTime>
#include <QJsonObject>
#include <QString>

namespace NativeDiagnostics {

QJsonObject buildServiceLogEvent(
    const QString &message,
    const QString &source = QStringLiteral("service"),
    const QString &level = QStringLiteral("info"),
    int sequenceId = 0,
    const QDateTime &generatedAt = {});

QJsonObject buildServiceTerminalCommandResult(
    bool accepted,
    const QString &command,
    const QString &output,
    const QString &source = QStringLiteral("terminal"),
    int exitCode = 0,
    const QDateTime &createdAt = {});

QString formatServiceLogLine(const QJsonObject &event);

} // namespace NativeDiagnostics
