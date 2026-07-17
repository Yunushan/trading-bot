#pragma once

#include <QDateTime>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QString>
#include <QStringList>

namespace NativeConfigPersistence {

inline constexpr const char *ServiceConfigFileKind = "trading-bot-service-config";
inline constexpr int ServiceConfigFormatVersion = 1;
inline constexpr const char *ServiceConfigEnvPath = "BOT_SERVICE_CONFIG_PATH";
// Deprecated legacy setting. It is intentionally ignored by persistence code.
inline constexpr const char *ServiceConfigAllowInlineSecretsEnv = "BOT_SERVICE_CONFIG_ALLOW_INLINE_SECRETS";
inline constexpr const char *ServiceConfigAllowUnsafePathEnv = "BOT_SERVICE_CONFIG_ALLOW_UNSAFE_PATH";
inline constexpr const char *ServiceConfigSecretStorage = "redacted-json-config";
inline constexpr const char *ServiceConfigSecretStorageWarning =
    "Secret values are redacted from this JSON config. Supply credentials through "
    "environment variables or OS credential storage.";

struct ServiceConfigLoadResult {
    bool ok = false;
    QJsonObject config;
    QJsonObject metadata;
    QString error;
};

struct ServiceConfigRuntimeState {
    bool loaded = false;
    bool dirty = false;
    QString lastLoadedAt;
    QString lastSavedAt;
    QJsonValue migratedFromFormatVersion = QJsonValue::Null;
};

struct ServiceConfigValidationResult {
    bool ok = false;
    QJsonObject config;
    QJsonArray issues;
    QString error;
};

bool serviceConfigEnvFlag(const QString &value, bool defaultValue = false);
QString serviceConfigDefaultPath();
QString resolveServiceConfigPath(const QString &path = {});
QString serviceConfigSafeRoot();
QString ensureServiceConfigPathAllowed(const QString &path = {}, bool allowUnsafePath = false);

bool isServiceConfigSecretKey(const QString &key);
QStringList serviceConfigSecretFieldPaths(const QJsonValue &payload);
QJsonObject serviceConfigSecretMetadata(const QJsonObject &config);
QJsonValue withoutInlineServiceConfigSecretValues(const QJsonValue &payload);

ServiceConfigValidationResult validateServiceRuntimeConfig(const QJsonObject &config);
QString formatServiceConfigValidationIssues(const QJsonArray &issues);
QJsonObject buildServiceConfigPersistencePayload(
    const QJsonObject &config,
    const QDateTime &savedAt = {},
    bool allowInlineSecrets = false);
ServiceConfigLoadResult coerceServiceConfigPersistencePayload(
    const QJsonValue &rawPayload,
    const QString &path = {});
ServiceConfigLoadResult loadServiceConfigFile(const QString &path = {});
QJsonObject writeServiceConfigFile(
    const QJsonObject &config,
    const QString &path = {},
    bool allowUnsafePath = false,
    bool allowInlineSecrets = false,
    const QDateTime &savedAt = {});
QJsonObject serviceConfigFileStatus(const QString &path = {});
QJsonObject buildServiceConfigPersistenceStatus(
    const QJsonObject &fileStatus,
    const ServiceConfigRuntimeState &runtimeState);

} // namespace NativeConfigPersistence
