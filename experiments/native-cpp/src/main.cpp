#include "TradingBotWindow.h"
#include "TradingBotWindowSupport.h"

#include <QApplication>
#include <QByteArray>
#include <QComboBox>
#include <QCoreApplication>
#include <QDir>
#include <QEvent>
#include <QEventLoop>
#include <QFileInfo>
#include <QGuiApplication>
#include <QIcon>
#include <QLabel>
#include <QListWidget>
#include <QTabBar>
#include <QStringList>
#include <QTabWidget>
#include <QTextStream>
#include <QTimer>

#include <memory>

#ifdef Q_OS_WIN
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif
#include <windows.h>
#include <shobjidl.h>
#endif

// Entrypoint notes:
// - Keep shell/taskbar identity stable on Windows.
// - Resolve icon from Qt resources first, then filesystem fallback.
// - Start the main window maximized to match Python-side UX defaults.
namespace {
QString findIconPath() {
    // Prefer the embedded Qt resource (always available after build)
    const QIcon resIcon(":/icons/crypto_forex_logo.png");
    if (!resIcon.isNull()) {
        return QString(":/icons/crypto_forex_logo.png");
    }

    QDir dir(QCoreApplication::applicationDirPath());
    const QStringList names = {"assets/crypto_forex_logo.png",
                               "assets/crypto_forex_logo.ico"};
    for (int i = 0; i < 6; ++i) {
        for (const auto &name : names) {
            const QFileInfo candidate(dir.filePath(name));
            if (candidate.isFile()) {
                return candidate.absoluteFilePath();
            }
        }
        dir.cdUp();
    }
    return {};
}

QIcon loadAppIcon() {
    const auto path = findIconPath();
    if (path.isEmpty()) {
        return QIcon();
    }
    QIcon icon(path);
    if (icon.isNull() && path.startsWith(":/")) {
        icon = QIcon(":/icons/crypto_forex_logo.png");
    }
    return icon;
}

bool hasBoundedSmokeArg() {
    const QStringList args = QCoreApplication::arguments();
    return args.contains(QStringLiteral("--smoke"))
        || args.contains(QStringLiteral("--healthcheck"));
}

bool verifyBoundedSmokeWindow(TradingBotWindow &window) {
    const QStringList expectedTabs = {
        QStringLiteral("Dashboard"),
        QStringLiteral("Chart"),
        QStringLiteral("Positions"),
        QStringLiteral("Backtest"),
        QStringLiteral("Liquidation Heatmap"),
        QStringLiteral("Code Languages"),
    };

    QTabWidget *mainTabs = nullptr;
    for (QTabWidget *candidate : window.findChildren<QTabWidget *>()) {
        if (candidate && candidate->count() == expectedTabs.size()) {
            bool matches = true;
            for (int index = 0; index < expectedTabs.size(); ++index) {
                if (candidate->tabText(index) != expectedTabs.at(index)) {
                    matches = false;
                    break;
                }
            }
            if (matches) {
                mainTabs = candidate;
                break;
            }
        }
    }
    if (!mainTabs) {
        QTextStream(stderr) << "Trading Bot C++ smoke failed: primary desktop tabs are unavailable\n";
        return false;
    }

    // The bounded smoke must remain independent of the browser runtime. A
    // successful QApplication launch alone would not catch an accidental
    // QWebEngineView construction because the failure occurs asynchronously.
    for (QObject *child : window.findChildren<QObject *>()) {
        const QString className = QString::fromLatin1(child->metaObject()->className());
        if (className.contains(QStringLiteral("WebEngine"), Qt::CaseInsensitive)) {
            QTextStream(stderr) << "Trading Bot C++ smoke failed: bounded smoke constructed "
                                << className << "\n";
            return false;
        }
    }
    if (!window.findChild<QWidget *>(QStringLiteral("nativeKlineChartFallback"))
        || !window.findChild<QLabel *>(QStringLiteral("chartTradingViewFallback"))
        || !window.findChild<QLabel *>(QStringLiteral("liquidationWebEngineFallback"))) {
        QTextStream(stderr) << "Trading Bot C++ smoke failed: bounded browser fallbacks are unavailable\n";
        return false;
    }

    auto verifyComboCatalog = [](QComboBox *combo,
                                 const QStringList &expectedKeys,
                                 const QStringList &expectedLabels,
                                 const QString &name) {
        if (!combo || combo->count() != expectedKeys.size() || combo->count() != expectedLabels.size()) {
            QTextStream(stderr) << "Trading Bot C++ smoke failed: " << name
                                << " does not expose the Python option catalog\n";
            return false;
        }
        for (int index = 0; index < expectedKeys.size(); ++index) {
            if (combo->itemData(index).toString() != expectedKeys.at(index)
                || combo->itemText(index) != expectedLabels.at(index)) {
                QTextStream(stderr) << "Trading Bot C++ smoke failed: " << name
                                    << " option key/label differs at index " << index << "\n";
                return false;
            }
        }
        return true;
    };

    if (!verifyComboCatalog(
            window.findChild<QComboBox *>(QStringLiteral("dashboardThemeCombo")),
            TradingBotWindowSupport::pythonSourceThemeOptionKeys(),
            TradingBotWindowSupport::pythonSourceThemeOptionLabels(),
            QStringLiteral("theme"))
        || !verifyComboCatalog(
            window.findChild<QComboBox *>(QStringLiteral("dashboardDesignCombo")),
            TradingBotWindowSupport::pythonSourceDesignOptionKeys(),
            TradingBotWindowSupport::pythonSourceDesignOptionLabels(),
            QStringLiteral("design"))) {
        return false;
    }

    auto *workspaceNavigation = window.findChild<QListWidget *>(QStringLiteral("workspaceNavigation"));
    auto *workspaceNavigationRail = window.findChild<QWidget *>(QStringLiteral("workspaceNavigationRail"));
    if (!workspaceNavigation || !workspaceNavigationRail || workspaceNavigation->count() != mainTabs->count()) {
        QTextStream(stderr) << "Trading Bot C++ smoke failed: workspace navigation is not synchronized\n";
        return false;
    }
    const int originalIndex = mainTabs->currentIndex();
    auto *designCombo = window.findChild<QComboBox *>(QStringLiteral("dashboardDesignCombo"));
    if (!designCombo) {
        QTextStream(stderr) << "Trading Bot C++ smoke failed: design selector is unavailable\n";
        return false;
    }
    const QString originalDesignKey = designCombo->currentData().toString();
    const int workstationIndex = designCombo->findData(QStringLiteral("Workstation"));
    const int classicIndex = designCombo->findData(QStringLiteral("Classic"));
    if (workstationIndex < 0 || classicIndex < 0) {
        QTextStream(stderr) << "Trading Bot C++ smoke failed: design keys are not synchronized\n";
        return false;
    }
    designCombo->setCurrentIndex(workstationIndex);
    QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    if (!window.property("workstationLayout").toBool()
        || workspaceNavigationRail->isHidden()
        || workspaceNavigation->isHidden()
        || !mainTabs->tabBar()->isHidden()) {
        QTextStream(stderr) << "Trading Bot C++ smoke failed: Workstation design was not applied"
                            << " (selected=" << designCombo->currentText()
                            << ", key=" << designCombo->currentData().toString()
                            << ", property=" << window.property("workstationLayout").toBool()
                            << ", railHidden=" << workspaceNavigationRail->isHidden()
                            << ", navigationHidden=" << workspaceNavigation->isHidden()
                            << ", tabbarHidden=" << mainTabs->tabBar()->isHidden() << ")\n";
        return false;
    }
    workspaceNavigation->setCurrentRow(2);
    QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    if (mainTabs->currentIndex() != 2 || workspaceNavigation->currentRow() != 2) {
        QTextStream(stderr) << "Trading Bot C++ smoke failed: workspace navigation did not select the tab\n";
        return false;
    }
    mainTabs->setCurrentIndex(4);
    QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    if (workspaceNavigation->currentRow() != 4) {
        QTextStream(stderr) << "Trading Bot C++ smoke failed: tab selection did not update workspace navigation\n";
        return false;
    }
    designCombo->setCurrentIndex(classicIndex);
    QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    if (window.property("workstationLayout").toBool()
        || !workspaceNavigationRail->isHidden()
        || !workspaceNavigation->isHidden()
        || mainTabs->tabBar()->isHidden()) {
        QTextStream(stderr) << "Trading Bot C++ smoke failed: Classic design was not restored\n";
        return false;
    }
    const int originalDesignIndex = designCombo->findData(originalDesignKey);
    if (originalDesignIndex >= 0) {
        designCombo->setCurrentIndex(originalDesignIndex);
    }
    mainTabs->setCurrentIndex(originalIndex);
    QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);

    for (int index = 0; index < expectedTabs.size(); ++index) {
        if (!mainTabs->widget(index)) {
            QTextStream(stderr) << "Trading Bot C++ smoke failed: "
                                << expectedTabs.at(index) << " page is unavailable\n";
            return false;
        }
        mainTabs->setCurrentIndex(index);
        QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents);
    }
    mainTabs->setCurrentIndex(0);
    return true;
}

int runBoundedSmoke(QApplication &app, const QIcon &icon) {
    app.setProperty("tradingBotBoundedSmoke", true);

    auto window = std::make_unique<TradingBotWindow>();
    if (!icon.isNull()) {
        window->setWindowIcon(icon);
    }

    TradingBotWindow *windowPtr = window.get();
    bool windowContractOk = true;
    QTimer::singleShot(0, windowPtr, [windowPtr, &windowContractOk]() {
        windowPtr->show();
        windowContractOk = verifyBoundedSmokeWindow(*windowPtr);
    });
    QTimer::singleShot(150, &app, &QCoreApplication::quit);

    const int exitCode = app.exec();
    window->close();
    window.reset();
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    QCoreApplication::processEvents(QEventLoop::AllEvents, 100);

    if (exitCode != 0) {
        QTextStream(stderr) << "Trading Bot C++ smoke failed with Qt exit code "
                            << exitCode << '\n';
        return exitCode;
    }
    if (!windowContractOk) {
        return 1;
    }
    QTextStream(stdout) << "Trading Bot C++ smoke ok\n";
    return 0;
}

#ifdef Q_OS_WIN
void applyAppUserModelID() {
    // Ensures taskbar pinning/grouping and jump-list identity stay consistent.
    const wchar_t *appid = L"TradingBot.Desktop.Cpp";
    SetCurrentProcessExplicitAppUserModelID(appid);
}
#endif
} // namespace

int main(int argc, char *argv[]) {
#ifdef Q_OS_WIN
    // Apply AppUserModelID before QApplication is created.
    applyAppUserModelID();
#endif

    QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);
    QApplication app(argc, argv);
    app.setApplicationDisplayName("Trading Bot");
    app.setApplicationName("Trading Bot");

    if (hasBoundedSmokeArg()) {
        // Keep packaging smoke output deterministic so the bundle verifier can reject real diagnostics.
        const QByteArray existingFlags = qgetenv("QTWEBENGINE_CHROMIUM_FLAGS");
        if (!existingFlags.contains("--disable-logging")) {
            const QByteArray separator = existingFlags.isEmpty() ? QByteArray() : QByteArray(" ");
            qputenv("QTWEBENGINE_CHROMIUM_FLAGS", existingFlags + separator + "--disable-logging --log-level=3");
        }
    }

    const QIcon icon = loadAppIcon();
    if (!icon.isNull()) {
        app.setWindowIcon(icon);
        QGuiApplication::setWindowIcon(icon);
    }

    if (hasBoundedSmokeArg()) {
        return runBoundedSmoke(app, icon);
    }

    TradingBotWindow window;
    if (!icon.isNull()) {
        window.setWindowIcon(icon);
    }

    window.showMaximized();

    return app.exec();
}
