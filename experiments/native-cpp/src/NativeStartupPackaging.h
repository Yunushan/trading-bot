#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QString>

namespace NativeStartupPackaging {

QString appUserModelId();
QString executableName();
QJsonObject desktopEntrypointContract();
QJsonObject serviceEntrypointContract();
QJsonObject cppStartupPackagingContract();
QJsonArray requiredStartupSuppressionEnv();
QJsonArray releaseSmokeCommands();
bool startupSuppressionEnvIsRequired(const QString &name);

} // namespace NativeStartupPackaging
