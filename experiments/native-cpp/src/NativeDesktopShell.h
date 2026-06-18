#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QString>
#include <QStringList>

namespace NativeDesktopShell {

QString lazySecondaryTabProperty();
QStringList desktopShellBoundaries();
QJsonArray desktopShellTabs();
QStringList primaryTabTitles();
QStringList lazySecondaryTabKeys();
int lazySecondaryTabLoadDelayMs(const QString &key, const QString &platform, const QString &envOverride = {});
bool lazySecondaryTabPrewarmEnabled(const QString &platform, const QString &envFlag = {});
QJsonObject buildDesktopStartupContract(const QString &platform, const QString &preloadFlag = {});
QJsonObject buildTabActivationEffect(
    const QString &tabKey,
    const QString &chartMode,
    bool safeChartMode,
    bool recentCodeSwitch,
    bool codeLanguageIsCpp);
QJsonObject normalizeDesktopTheme(const QString &name);
QJsonObject cppDesktopShellOwnershipContract();

} // namespace NativeDesktopShell
