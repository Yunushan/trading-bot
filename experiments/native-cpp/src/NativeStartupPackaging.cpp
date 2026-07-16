#include "NativeStartupPackaging.h"

#include <QJsonValue>

namespace {

QJsonObject entrypointContract(
    const QString &product,
    const QString &canonicalRepoPath,
    const QString &canonicalModule,
    const QString &installedCommand,
    const QString &compatibilityEntrypoint) {
    return {
        {QStringLiteral("product"), product},
        {QStringLiteral("canonical_repo_path"), canonicalRepoPath},
        {QStringLiteral("canonical_module"), canonicalModule},
        {QStringLiteral("installed_command"), installedCommand},
        {QStringLiteral("compatibility_entrypoint"), compatibilityEntrypoint},
        {QStringLiteral("compatibility_status"), QStringLiteral("deprecated")},
        {QStringLiteral("compatibility_notice"),
         QStringLiteral("Deprecated compatibility %1 entrypoint remains available via '%2'. Prefer '%3' or the installed command '%4'.")
             .arg(product, compatibilityEntrypoint, canonicalRepoPath, installedCommand)},
    };
}

} // namespace

namespace NativeStartupPackaging {

QString appUserModelId() {
    return QStringLiteral("TradingBot.Desktop.Cpp");
}

QString executableName() {
    return QStringLiteral("Trading-Bot-C++");
}

QJsonObject desktopEntrypointContract() {
    return entrypointContract(
        QStringLiteral("desktop"),
        QStringLiteral("apps/desktop-pyqt/main.py"),
        QStringLiteral("app.desktop.product_main"),
        QStringLiteral("trading-bot-desktop"),
        QStringLiteral("Languages/Python/main.py"));
}

QJsonObject serviceEntrypointContract() {
    return entrypointContract(
        QStringLiteral("service"),
        QStringLiteral("apps/service-api/main.py"),
        QStringLiteral("app.service.product_main"),
        QStringLiteral("trading-bot-service"),
        QStringLiteral("python -m app.service.main"));
}

QJsonArray requiredStartupSuppressionEnv() {
    return {
        QStringLiteral("BOT_DISABLE_PYTHONW_RELAUNCH"),
        QStringLiteral("BOT_DISABLE_PUBLIC_SHELL_SHORTCUT_LAUNCH"),
    };
}

QJsonArray releaseSmokeCommands() {
    return {
        QStringLiteral("cmake --build build/binance_cpp --config Release"),
        QStringLiteral("build/binance_cpp/Release/Trading-Bot-C++.exe --smoke"),
    };
}

QJsonObject cppStartupPackagingContract() {
    return {
        {QStringLiteral("native_surface"), QStringLiteral("cpp-qt")},
        {QStringLiteral("product_name"), executableName()},
        {QStringLiteral("identifier"), appUserModelId()},
        {QStringLiteral("app_user_model_id"), appUserModelId()},
        {QStringLiteral("icon_resource"), QStringLiteral(":/app_icon.ico")},
        {QStringLiteral("startup_suppression_env"), requiredStartupSuppressionEnv()},
        {QStringLiteral("release_smoke_commands"), releaseSmokeCommands()},
        {QStringLiteral("delegates_trading_execution_to_python"), false},
        {QStringLiteral("native_trading_execution_scope"), QStringLiteral("binance-usds-and-coin-futures")},
    };
}

bool startupSuppressionEnvIsRequired(const QString &name) {
    const QString expected = name.trimmed();
    for (const QJsonValue &value : requiredStartupSuppressionEnv()) {
        if (value.toString() == expected) {
            return true;
        }
    }
    return false;
}

} // namespace NativeStartupPackaging
