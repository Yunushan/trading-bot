#include "BacktestWindow.h"

#include <QApplication>

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);

    BacktestWindow window;
    window.show();

    return app.exec();
}
