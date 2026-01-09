#include "BacktestWindow.h"

#include <QApplication>
#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QGuiApplication>
#include <QIcon>

#ifdef Q_OS_WIN
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif
#include <windows.h>
#include <shobjidl.h>
#endif

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

#ifdef Q_OS_WIN
void applyAppUserModelID() {
    // Ensures taskbar pinning and icon association work consistently on Windows.
    const wchar_t *appid = L"Binance.TradingBot.Cpp";
    SetCurrentProcessExplicitAppUserModelID(appid);
}
#endif
} // namespace

int main(int argc, char *argv[]) {
#ifdef Q_OS_WIN
    applyAppUserModelID();
#endif

    QApplication app(argc, argv);
    app.setApplicationDisplayName("Binance Trading Bot");
    app.setApplicationName("Binance Trading Bot");

    const QIcon icon = loadAppIcon();
    if (!icon.isNull()) {
        app.setWindowIcon(icon);
        QGuiApplication::setWindowIcon(icon);
    }

    BacktestWindow window;
    if (!icon.isNull()) {
        window.setWindowIcon(icon);
    }
    window.show();

    return app.exec();
}
