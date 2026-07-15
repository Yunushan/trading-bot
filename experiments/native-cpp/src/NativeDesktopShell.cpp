#include "NativeDesktopShell.h"

#include <QJsonArray>

#include <algorithm>

namespace {

QJsonObject tab(
    const QString &key,
    const QString &title,
    const QString &loadPolicy,
    const QString &placeholder,
    const QStringList &hooks) {
    QJsonArray hookArray;
    for (const QString &hook : hooks) {
        hookArray.append(hook);
    }
    return {
        {QStringLiteral("key"), key},
        {QStringLiteral("title"), title},
        {QStringLiteral("load_policy"), loadPolicy},
        {QStringLiteral("placeholder_message"), placeholder},
        {QStringLiteral("activation_hooks"), hookArray},
    };
}

QJsonArray stringArray(const QStringList &values) {
    QJsonArray array;
    for (const QString &value : values) {
        array.append(value);
    }
    return array;
}

QString titleCase(const QString &value) {
    if (value.isEmpty()) {
        return {};
    }
    QString result = value.toLower();
    result[0] = result[0].toUpper();
    return result;
}

} // namespace

namespace NativeDesktopShell {

QString lazySecondaryTabProperty() {
    return QStringLiteral("_bot_lazy_secondary_tab_key");
}

QStringList desktopShellBoundaries() {
    return {
        QStringLiteral("Dashboard-first startup composition"),
        QStringLiteral("Chart, Positions, Backtest, Liquidation Heatmap, and Code Languages primary tab order"),
        QStringLiteral("Backtest, Liquidation Heatmap, and Code Languages lazy placeholder lifecycle"),
        QStringLiteral("Code tab window-suppression and dependency auto-refresh hooks"),
        QStringLiteral("Chart safe-mode and code-to-chart deferred reload hooks"),
        QStringLiteral("Theme persistence and chart-theme forwarding"),
        QStringLiteral("C++ Qt shell ownership with native Binance USD-M Futures execution"),
    };
}

QJsonArray desktopShellTabs() {
    return {
        tab(
            QStringLiteral("dashboard"),
            QStringLiteral("Dashboard"),
            QStringLiteral("startup"),
            {},
            {QStringLiteral("dashboard_runtime_state"), QStringLiteral("dashboard_chart_section")}),
        tab(
            QStringLiteral("chart"),
            QStringLiteral("Chart"),
            QStringLiteral("startup"),
            {},
            {
                QStringLiteral("chart_safe_mode_guard"),
                QStringLiteral("tradingview_external_fallback"),
                QStringLiteral("lightweight_chart_refresh"),
                QStringLiteral("dashboard_selection_auto_follow"),
            }),
        tab(
            QStringLiteral("positions"),
            QStringLiteral("Positions"),
            QStringLiteral("startup"),
            {},
            {QStringLiteral("positions_table_refresh"), QStringLiteral("closed_history_reconciliation")}),
        tab(
            QStringLiteral("backtest"),
            QStringLiteral("Backtest"),
            QStringLiteral("lazy-placeholder"),
            QStringLiteral("Backtest tools load the first time you open this tab."),
            {
                QStringLiteral("create_backtest_tab"),
                QStringLiteral("refresh_symbol_interval_pairs"),
                QStringLiteral("initialize_backtest_ui_defaults"),
                QStringLiteral("update_connector_labels"),
            }),
        tab(
            QStringLiteral("liquidation"),
            QStringLiteral("Liquidation Heatmap"),
            QStringLiteral("lazy-placeholder"),
            QStringLiteral("Liquidation heatmaps load the first time you open this tab."),
            {QStringLiteral("init_liquidation_heatmap_tab")}),
        tab(
            QStringLiteral("code"),
            QStringLiteral("Code Languages"),
            QStringLiteral("lazy-placeholder"),
            QStringLiteral("Code language tools load the first time you open this tab."),
            {
                QStringLiteral("start_code_tab_window_suppression"),
                QStringLiteral("init_code_language_tab"),
                QStringLiteral("dependency_usage_auto_poll"),
                QStringLiteral("dependency_versions_auto_refresh"),
            }),
    };
}

QStringList primaryTabTitles() {
    QStringList titles;
    for (const QJsonValue &value : desktopShellTabs()) {
        titles.append(value.toObject().value(QStringLiteral("title")).toString());
    }
    return titles;
}

QStringList lazySecondaryTabKeys() {
    QStringList keys;
    for (const QJsonValue &value : desktopShellTabs()) {
        const QJsonObject item = value.toObject();
        if (item.value(QStringLiteral("load_policy")).toString() == QStringLiteral("lazy-placeholder")) {
            keys.append(item.value(QStringLiteral("key")).toString());
        }
    }
    return keys;
}

int lazySecondaryTabLoadDelayMs(const QString &key, const QString &platform, const QString &envOverride) {
    if (key.trimmed().toLower() != QStringLiteral("code")) {
        return 0;
    }
    const int defaultDelay = platform.compare(QStringLiteral("win32"), Qt::CaseInsensitive) == 0
            || platform.compare(QStringLiteral("windows"), Qt::CaseInsensitive) == 0
        ? 90
        : 0;
    bool ok = false;
    const int parsed = envOverride.trimmed().toInt(&ok);
    return std::max(0, std::min(ok ? parsed : defaultDelay, 1000));
}

bool lazySecondaryTabPrewarmEnabled(const QString &platform, const QString &envFlag) {
    if (platform.compare(QStringLiteral("win32"), Qt::CaseInsensitive) != 0
        && platform.compare(QStringLiteral("windows"), Qt::CaseInsensitive) != 0) {
        return false;
    }
    const QString flag = (envFlag.isEmpty() ? QStringLiteral("0") : envFlag).trimmed().toLower();
    return !QStringList{QStringLiteral("0"), QStringLiteral("false"), QStringLiteral("no"), QStringLiteral("off")}.contains(flag);
}

QJsonObject buildDesktopStartupContract(const QString &platform, const QString &preloadFlag) {
    return {
        {QStringLiteral("root_widget"), QStringLiteral("QTabWidget")},
        {QStringLiteral("startup_tab"), QStringLiteral("Dashboard")},
        {QStringLiteral("tab_bar_event_filter"), true},
        {QStringLiteral("current_changed_handler"), QStringLiteral("_on_tab_changed")},
        {QStringLiteral("tab_bar_clicked_handler"), QStringLiteral("_on_tab_bar_clicked")},
        {QStringLiteral("lazy_property"), lazySecondaryTabProperty()},
        {QStringLiteral("lazy_tabs"), stringArray(lazySecondaryTabKeys())},
        {QStringLiteral("prewarm_keys"), stringArray({QStringLiteral("code"), QStringLiteral("backtest")})},
        {QStringLiteral("prewarm_enabled"), lazySecondaryTabPrewarmEnabled(platform, preloadFlag)},
        {QStringLiteral("first_visible_sections"),
         stringArray({
             QStringLiteral("Dashboard header"),
             QStringLiteral("Markets & Intervals"),
             QStringLiteral("Strategy Controls"),
             QStringLiteral("Indicators"),
             QStringLiteral("Symbol / Interval Overrides"),
             QStringLiteral("Desktop Service API"),
             QStringLiteral("Logs"),
         })},
    };
}

QJsonObject buildTabActivationEffect(
    const QString &tabKey,
    const QString &chartMode,
    bool safeChartMode,
    bool recentCodeSwitch,
    bool codeLanguageIsCpp) {
    const QString key = tabKey.trimmed().toLower();
    if (key == QStringLiteral("code")) {
        return {
            {QStringLiteral("tab"), QStringLiteral("code")},
            {QStringLiteral("start_dependency_usage_auto_poll"), true},
            {QStringLiteral("schedule_dependency_versions_auto_refresh"), true},
            {QStringLiteral("start_code_tab_window_suppression"), true},
            {QStringLiteral("maybe_auto_prepare_cpp_environment"), codeLanguageIsCpp},
            {QStringLiteral("cancel_code_auto_refresh"), false},
        };
    }
    if (key == QStringLiteral("chart")) {
        const QString mode = chartMode.trimmed().toLower();
        const bool guarded = safeChartMode
            && QStringList{QStringLiteral("tradingview"), QStringLiteral("original"), QStringLiteral("lightweight")}.contains(mode);
        return {
            {QStringLiteral("tab"), QStringLiteral("chart")},
            {QStringLiteral("stop_dependency_usage_auto_poll"), true},
            {QStringLiteral("cancel_code_auto_refresh"), true},
            {QStringLiteral("safe_mode_redirect"), guarded},
            {QStringLiteral("defer_after_code_switch"), recentCodeSwitch},
            {QStringLiteral("load_chart"), true},
            {QStringLiteral("dashboard_selection_auto_follow"), true},
        };
    }
    if (key == QStringLiteral("backtest") || key == QStringLiteral("liquidation")) {
        return {
            {QStringLiteral("tab"), key},
            {QStringLiteral("lazy_load_on_first_open"), true},
            {QStringLiteral("only_if_current"), false},
            {QStringLiteral("cancel_code_auto_refresh"), true},
        };
    }
    return {
        {QStringLiteral("tab"), key},
        {QStringLiteral("stop_dependency_usage_auto_poll"), true},
        {QStringLiteral("cancel_code_auto_refresh"), true},
    };
}

QJsonObject normalizeDesktopTheme(const QString &name) {
    QString normalized = name.trimmed().toLower();
    if (normalized == QStringLiteral("gren")) {
        normalized = QStringLiteral("green");
    }
    const bool dark = normalized.startsWith(QStringLiteral("dark"))
        || QStringList{
               QStringLiteral("blue"),
               QStringLiteral("yellow"),
               QStringLiteral("green"),
               QStringLiteral("red"),
           }.contains(normalized);
    QString accent;
    if (normalized == QStringLiteral("blue")) accent = QStringLiteral("#3b82f6");
    else if (normalized == QStringLiteral("yellow")) accent = QStringLiteral("#f59e0b");
    else if (normalized == QStringLiteral("green")) accent = QStringLiteral("#22c55e");
    else if (normalized == QStringLiteral("red")) accent = QStringLiteral("#ef4444");
    return {
        {QStringLiteral("requested"), name},
        {QStringLiteral("stored_name"), normalized.isEmpty() ? QStringLiteral("Dark") : titleCase(normalized)},
        {QStringLiteral("palette"), dark ? QStringLiteral("dark") : QStringLiteral("light")},
        {QStringLiteral("chart_theme"), dark ? QStringLiteral("dark") : QStringLiteral("light")},
        {QStringLiteral("accent_color"), accent.isEmpty() ? QJsonValue() : QJsonValue(accent)},
    };
}

QJsonObject cppDesktopShellOwnershipContract() {
    return {
        {QStringLiteral("status"), QStringLiteral("production-qt-shell-parity-contract")},
        {QStringLiteral("owns_desktop_tab_lifecycle"), true},
        {QStringLiteral("owns_release_entrypoint"), true},
        {QStringLiteral("owns_trading_execution"), true},
        {QStringLiteral("native_trading_execution_scope"), QStringLiteral("binance-usds-futures")},
        {QStringLiteral("primary_tabs"), stringArray(primaryTabTitles())},
        {QStringLiteral("execution_boundary"), QStringLiteral("The C++ runtime owns Binance USD-M Futures execution; unimplemented venues remain evidence-gated and unsupported by the native order path.")},
    };
}

} // namespace NativeDesktopShell
