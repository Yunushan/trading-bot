#pragma once

#include <QJsonObject>
#include <QString>
#include <QStringList>

namespace NativeLlmAdvisory {

QString executionBoundaryText();

QJsonObject buildPromptRoutePayload(
    const QString &prompt,
    const QString &systemPrompt = {},
    bool dryRun = true,
    const QString &source = QStringLiteral("cpp-desktop-llm"));

QJsonObject buildLocalModelRoutePayload(
    const QString &baseUrl,
    const QString &model,
    const QString &source = QStringLiteral("cpp-desktop-llm-local-model"));

QString describeLocalModelStatus(const QJsonObject &status, const QString &fallbackModel = {});

QStringList outputPolicyViolations(const QString &text);

QJsonObject renderPromptResult(const QJsonObject &response);

} // namespace NativeLlmAdvisory
