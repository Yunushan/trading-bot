#include "../src/TradingBotWindow.h"

#include <QApplication>
#include <QAbstractButton>
#include <QCheckBox>
#include <QComboBox>
#include <QDir>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLineEdit>
#include <QLabel>
#include <QMessageBox>
#include <QNetworkProxy>
#include <QPushButton>
#include <QSignalBlocker>
#include <QStandardPaths>
#include <QTableWidget>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTextStream>
#include <QTimer>
#include <QUrlQuery>

#include <algorithm>
#include <functional>

class NativePositionCloseTests {
public:
    int run(bool stopAccountingOnly = false) {
        QTcpServer proxy;
        if (!proxy.listen(QHostAddress::LocalHost, 0)) return 2;
        int networkRequests = 0;
        ExchangeReply exchangeReply;
        QObject::connect(&proxy, &QTcpServer::newConnection, &proxy, [&]() {
            while (proxy.hasPendingConnections()) {
                auto *socket = proxy.nextPendingConnection();
                QObject::connect(socket, &QTcpSocket::disconnected, socket, &QObject::deleteLater);
                QObject::connect(socket, &QTcpSocket::readyRead, socket, [&, socket]() {
                    if (socket->property("handled").toBool()) return;
                    const QByteArray request = socket->property("request").toByteArray() + socket->readAll();
                    socket->setProperty("request", request);
                    if (!request.contains("\r\n\r\n")) return;
                    socket->setProperty("handled", true);
                    ++networkRequests;
                    const auto firstLine = request.left(request.indexOf("\r\n")).split(' ');
                    const QUrl url = QUrl::fromEncoded(firstLine.value(1));
                    if (exchangeReply && firstLine.value(0) != "CONNECT"
                        && (url.isRelative() || (url.host() == QStringLiteral("127.0.0.1")
                                                && url.port() == proxy.serverPort()))) {
                        const QByteArray body = exchangeReply(firstLine.value(0), url);
                        if (!body.isEmpty()) {
                            socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                                          + QByteArray::number(body.size()) + "\r\nConnection: close\r\n\r\n" + body);
                            socket->disconnectFromHost();
                            return;
                        }
                    }
                    // Never forward CONNECT or other requests to an external host.
                    socket->write("HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
                    socket->disconnectFromHost();
                });
            }
        });
        const auto previousProxy = QNetworkProxy::applicationProxy();
        QNetworkProxy::setApplicationProxy(QNetworkProxy(QNetworkProxy::HttpProxy,
            QStringLiteral("127.0.0.1"), proxy.serverPort()));
        qputenv("BOT_DESKTOP_SERVICE_API_BASE_URL",
            QStringLiteral("http://127.0.0.1:%1").arg(proxy.serverPort()).toUtf8());

        checkStopAllocationAccounting(proxy.serverPort(), exchangeReply);
        if (stopAccountingOnly) {
            QNetworkProxy::setApplicationProxy(previousProxy);
            QTextStream(stdout) << "Native stop accounting checks: " << failures_ << " failure(s)\n";
            return failures_ ? 1 : 0;
        }

        for (bool futures : {false, true}) {
            for (bool closeAll : {false, true}) {
                for (const QString &state : {QStringLiteral("unknown"), QStringLiteral("partial"),
                         QStringLiteral("in-flight"), QStringLiteral("stop"),
                         QStringLiteral("cycle"), QStringLiteral("stopping"), QStringLiteral("ready")}) {
                    TradingBotWindow window;
                    configure(window, futures);
                    auto *button = findButton(window, closeAll);
                    check(button != nullptr, QStringLiteral("close button exists"));
                    if (!button) continue;
                    const QString label = QStringLiteral("%1/%2/%3")
                        .arg(futures ? QStringLiteral("futures") : QStringLiteral("spot"),
                             closeAll ? QStringLiteral("all") : QStringLiteral("selected"), state);
                    if (state == QStringLiteral("unknown") || state == QStringLiteral("partial")) {
                        window.dashboardOrderExecutionSession_.submit(1.0, [&]() {
                            auto result = uncertain(state == QStringLiteral("partial"));
                            return result;
                        });
                    }
                    window.dashboardRuntimeStopRequested_ = state == QStringLiteral("stop");
                    window.dashboardRuntimeCycleInProgress_ = state == QStringLiteral("cycle");
                    window.dashboardRuntimeStopping_ = state == QStringLiteral("stopping");
                    const int before = networkRequests;
                    const auto click = [&]() {
                        QTimer dialogTimer;
                        dialogTimer.setInterval(1);
                        QObject::connect(&dialogTimer, &QTimer::timeout, &window, [&]() {
                            for (QWidget *widget : QApplication::topLevelWidgets()) {
                                if (auto *dialog = qobject_cast<QMessageBox *>(widget)) {
                                    if (auto *yes = dialog->button(QMessageBox::Yes)) yes->click();
                                }
                            }
                        });
                        dialogTimer.start();
                        button->click();
                    };
                    if (state == QStringLiteral("in-flight")) {
                        window.dashboardOrderExecutionSession_.submit(1.0, [&]() {
                            click();
                            return uncertain(false);
                        });
                    } else {
                        click();
                    }
                    if (state == QStringLiteral("ready")) {
                        check(networkRequests > before, label + QStringLiteral(": healthy control must reach the rejecting proxy"));
                        if (!futures && !closeAll) {
                            check(window.dashboardOrderExecutionSession_.reconciliationRequired(),
                                  label + QStringLiteral(": unacknowledged manual Spot POST must latch the shared barrier"));
                            const int afterSubmission = networkRequests;
                            click();
                            check(networkRequests == afterSubmission,
                                  label + QStringLiteral(": repeated manual request must not retry an uncertain order"));
                        }
                    } else {
                        check(networkRequests == before, label + QStringLiteral(": blocked action must issue no network requests"));
                        check(window.statusLabel_->text().startsWith(QStringLiteral("Position close blocked:")),
                              label + QStringLiteral(": reject through the action guard, not incidental validation"));
                    }
                    check(window.positionsTable_->rowCount() == 1
                              && window.positionsTable_->item(0, 16)->text() == QStringLiteral("OPEN"),
                          label + QStringLiteral(": blocked action must retain the open row"));
                    check(window.dashboardRuntimeOpenPositions_.size() == 1,
                          label + QStringLiteral(": blocked action must retain runtime exposure"));
                    if (state == QStringLiteral("partial")) {
                        check(window.dashboardOrderExecutionSession_.unresolvedOrder()->confirmedExecutedQuantity(1.0) == 0.25,
                              label + QStringLiteral(": earlier confirmed fill must not be erased or replayed"));
                    }
                    check(!window.positionsCloseInProgress_, label + QStringLiteral(": action guard must be released"));
                }
            }
            TradingBotWindow window;
            configure(window, futures);
            auto *selectedButton = findButton(window, false);
            auto *allButton = findButton(window, true);
            check(selectedButton && allButton, QStringLiteral("modal race controls exist"));
            if (!selectedButton || !allButton) continue;
            const int before = networkRequests;
            bool confirmed = false;
            QTimer dialogTimer;
            dialogTimer.setInterval(1);
            QObject::connect(&dialogTimer, &QTimer::timeout, &window, [&]() {
                if (confirmed) return;
                for (QWidget *widget : QApplication::topLevelWidgets()) {
                    auto *dialog = qobject_cast<QMessageBox *>(widget);
                    if (!dialog || !dialog->button(QMessageBox::Yes)) continue;
                    confirmed = true;
                    allButton->click();
                    check(window.statusLabel_->text().startsWith(QStringLiteral("Position close blocked:")),
                          QStringLiteral("nested close-all must not enter during selected-close confirmation"));
                    window.startDashboardRuntime();
                    check(!window.dashboardRuntimeActive_, QStringLiteral("start cannot race a manual close"));
                    window.dashboardOrderExecutionSession_.submit(1.0, []() { return uncertain(false); });
                    dialog->button(QMessageBox::Yes)->click();
                }
            });
            dialogTimer.start();
            selectedButton->click();
            dialogTimer.stop();
            check(confirmed, QStringLiteral("modal race fixture must confirm an actual selected-close dialog"));
            check(networkRequests == before, QStringLiteral("a new uncertainty barrier during confirmation must prevent submission"));
            check(!window.positionsCloseInProgress_, QStringLiteral("modal race must release the action guard"));
        }
        {
            TradingBotWindow window;
            configure(window, true);
            setCombo(window.dashboardModeCombo_, QStringLiteral("Paper Local"));
            window.dashboardRuntimeActive_ = true;
            const int before = networkRequests;
            check(window.beginPositionCloseAction(), QStringLiteral("paper stop fixture acquires a close action"));
            window.stopDashboardRuntime();
            check(window.dashboardRuntimeStopRequested_ && window.dashboardRuntimeActive_,
                  QStringLiteral("stop is deferred until the manual action accounts for its result"));
            window.finishPositionCloseAction();
            check(!window.positionsCloseInProgress_ && !window.dashboardRuntimeStopRequested_
                      && !window.dashboardRuntimeActive_,
                  QStringLiteral("finishing a manual action drains the deferred stop"));
            check(networkRequests == before, QStringLiteral("paper stop fixture must remain local"));
        }
        QNetworkProxy::setApplicationProxy(previousProxy);
        QTextStream(stdout) << "Native position close checks: " << failures_ << " failure(s)\n";
        return failures_ ? 1 : 0;
    }

private:
    using ExchangeReply = std::function<QByteArray(const QByteArray &, const QUrl &)>;
    int failures_ = 0;

    void checkStopAllocationAccounting(quint16 port, ExchangeReply &reply) {
        struct Scenario {
            QString name;
            double liveQty;
            double fill;
            bool visible = true;
            bool snapshotFails = false;
            bool shared = false;
            bool shortSide = false;
        };
        const QList<Scenario> scenarios{
            {QStringLiteral("aggregate-larger-partial"), 5.0, 1.0},
            {QStringLiteral("aggregate-smaller-partial"), 1.0, 0.5},
            {QStringLiteral("aggregate-equal-partial"), 2.0, 1.0},
            {QStringLiteral("aggregate-larger-full"), 5.0, 2.0},
            {QStringLiteral("no-visible-row-partial"), 5.0, 1.0, false},
            {QStringLiteral("http-failure"), 5.0, 0.0},
            {QStringLiteral("snapshot-failure"), 5.0, 0.0, true, true},
            {QStringLiteral("shared-partial"), 5.0, 1.0, true, false, true},
            {QStringLiteral("shared-full"), 5.0, 2.0, true, false, true},
            {QStringLiteral("short-partial"), 5.0, 1.0, true, false, false, true},
            {QStringLiteral("short-full"), 5.0, 2.0, true, false, false, true},
        };
        for (const auto &scenario : scenarios) {
            TradingBotWindow window;
            configure(window, true);
            setCombo(window.positionsViewCombo_, QStringLiteral("Per Trade View"));
            window.dashboardRuntimeActive_ = true;
            window.dashboardStopWithoutCloseCheck_->setChecked(false);
            setCombo(window.dashboardPositionModeCombo_, QStringLiteral("Hedge"));
            const QString base = QStringLiteral("http://127.0.0.1:%1").arg(port);
            const QString key = QStringLiteral("BTCUSDT|1m|fixture|%1").arg(base);
            const QString direction = scenario.shortSide ? QStringLiteral("SHORT") : QStringLiteral("LONG");
            const QString closeSide = scenario.shortSide ? QStringLiteral("BUY") : QStringLiteral("SELL");
            window.dashboardRuntimeOpenPositions_.clear();
            TradingBotWindow::RuntimePosition owned;
            owned.side = direction;
            owned.interval = QStringLiteral("1m");
            owned.connectorKey = QStringLiteral("fixture");
            owned.connectorBaseUrl = base;
            owned.quantity = 2.0;
            owned.entryPrice = 100.0;
            owned.leverage = 2.0;
            owned.displayMarginUsdt = 100.0;
            owned.roiBasisUsdt = 80.0;
            window.dashboardRuntimeOpenPositions_.insert(key, owned);
            const QString otherKey = QStringLiteral("BTCUSDT|5m|fixture|%1").arg(base);
            if (scenario.shared) {
                auto other = owned;
                other.interval = QStringLiteral("5m");
                other.quantity = 3.0;
                other.displayMarginUsdt = 150.0;
                other.roiBasisUsdt = 120.0;
                window.dashboardRuntimeOpenPositions_.insert(otherKey, other);
            }
            auto *table = window.positionsTable_;
            table->setRowCount(scenario.visible ? (scenario.shared ? 4 : 3) : 0);
            for (int row = 0; row < table->rowCount(); ++row) {
                for (int col = 0; col < table->columnCount(); ++col) {
                    auto *item = new QTableWidgetItem();
                    table->setItem(row, col, item);
                }
                const auto cell = [&](int col, const QString &value) {
                    table->item(row, col)->setText(value);
                    table->item(row, col)->setData(Qt::UserRole, value);
                };
                cell(0, QStringLiteral("BTCUSDT"));
                cell(2, QStringLiteral("120"));
                cell(5, QString::number(row == 0 ? 100 : 300));
                cell(6, QString::number(row == 0 ? 2 : 3));
                cell(8, row == 3 ? QStringLiteral("5m") : QStringLiteral("1m"));
                cell(12, row == 1 ? (scenario.shortSide ? QStringLiteral("LONG") : QStringLiteral("SHORT")) : direction);
                cell(16, QStringLiteral("OPEN"));
                cell(17, row == 2 ? QStringLiteral("Native [fixture-alt]") : QStringLiteral("Native [fixture]"));
                table->item(row, 6)->setData(Qt::UserRole + 2, row == 0 ? 2.0 : 3.0);
                table->item(row, 6)->setData(Qt::UserRole + 4, row == 0 ? 2.0 : 3.0);
                table->item(row, 5)->setData(Qt::UserRole + 2, row == 0 ? 100.0 : 300.0);
                table->item(row, 5)->setData(Qt::UserRole + 4, row == 0 ? 100.0 : 300.0);
            }
            int posts = 0;
            int snapshots = 0;
            const double requestQty = std::min(2.0, scenario.liveQty);
            double liveRemaining = scenario.liveQty;
            reply = [&](const QByteArray &method, const QUrl &url) -> QByteArray {
                const QUrlQuery query(url);
                QJsonDocument response;
                if (method == "GET" && url.path() == QStringLiteral("/fapi/v2/positionRisk")) {
                    ++snapshots;
                    if (scenario.snapshotFails) return {};
                    response = QJsonDocument(QJsonArray{QJsonObject{
                        {QStringLiteral("symbol"), QStringLiteral("BTCUSDT")},
                        {QStringLiteral("positionSide"), direction},
                        {QStringLiteral("positionAmt"), QString::number(scenario.shortSide ? -liveRemaining : liveRemaining)},
                        {QStringLiteral("entryPrice"), QStringLiteral("90")},
                        {QStringLiteral("markPrice"), QStringLiteral("120")},
                        {QStringLiteral("leverage"), QStringLiteral("5")},
                        {QStringLiteral("isolatedWallet"), QStringLiteral("400")},
                        {QStringLiteral("positionInitialMargin"), QStringLiteral("200")},
                    }});
                } else if (method == "GET" && url.path() == QStringLiteral("/fapi/v2/account")) {
                    response = QJsonDocument(QJsonObject{{QStringLiteral("positions"), QJsonArray{}}});
                } else if (method == "GET" && url.path() == QStringLiteral("/fapi/v1/exchangeInfo")) {
                    response = QJsonDocument(QJsonObject{{QStringLiteral("symbols"), QJsonArray{QJsonObject{
                        {QStringLiteral("symbol"), QStringLiteral("BTCUSDT")},
                        {QStringLiteral("quantityPrecision"), 2},
                        {QStringLiteral("pricePrecision"), 2},
                        {QStringLiteral("filters"), QJsonArray{
                            QJsonObject{{QStringLiteral("filterType"), QStringLiteral("LOT_SIZE")},
                                        {QStringLiteral("minQty"), QStringLiteral("0.25")},
                                        {QStringLiteral("maxQty"), QStringLiteral("100")},
                                        {QStringLiteral("stepSize"), QStringLiteral("0.25")}},
                            QJsonObject{{QStringLiteral("filterType"), QStringLiteral("PRICE_FILTER")},
                                        {QStringLiteral("tickSize"), QStringLiteral("0.01")}},
                        }},
                    }}}});
                } else if (method == "DELETE" && url.path() == QStringLiteral("/fapi/v1/allOpenOrders")) {
                    response = QJsonDocument(QJsonObject{{QStringLiteral("code"), 200}});
                } else if (method == "POST" && url.path() == QStringLiteral("/fapi/v1/order")) {
                    ++posts;
                    const double expectedRequest = posts == 1 ? requestQty : 3.0;
                    check(query.queryItemValue(QStringLiteral("quantity")).toDouble() == expectedRequest,
                          scenario.name + QStringLiteral(": POST quantity must not exceed allocation or live exposure"));
                    check(query.queryItemValue(QStringLiteral("side")) == closeSide
                              && query.queryItemValue(QStringLiteral("positionSide")) == direction,
                          scenario.name + QStringLiteral(": request must retain directional scope"));
                    if (scenario.fill == 0.0) return {};
                    const double fill = posts == 1 ? scenario.fill : 3.0;
                    liveRemaining -= fill;
                    response = QJsonDocument(QJsonObject{
                        {QStringLiteral("symbol"), QStringLiteral("BTCUSDT")},
                        {QStringLiteral("side"), closeSide},
                        {QStringLiteral("positionSide"), direction},
                        {QStringLiteral("clientOrderId"), query.queryItemValue(QStringLiteral("newClientOrderId"))},
                        {QStringLiteral("orderId"), QString::number(8000 + posts)},
                        {QStringLiteral("status"), fill == expectedRequest ? QStringLiteral("FILLED") : QStringLiteral("CANCELED")},
                        {QStringLiteral("executedQty"), QString::number(fill)},
                        {QStringLiteral("avgPrice"), QStringLiteral("120")},
                    });
                } else {
                    check(false, scenario.name + QStringLiteral(": unexpected fixture route: ") + url.path());
                    return {};
                }
                return response.toJson(QJsonDocument::Compact);
            };
            window.stopDashboardRuntime();
            reply = {};
            check(snapshots >= 1, scenario.name + QStringLiteral(": real stop lifecycle must fetch the snapshot"));
            check(posts == (scenario.snapshotFails ? 0 : (scenario.shared && scenario.fill == 2.0 ? 2 : 1)),
                  scenario.name + QStringLiteral(": stop must bound concrete order POSTs"));
            const double remaining = 2.0 - scenario.fill;
            if (remaining == 0.0) {
                check(!window.dashboardRuntimeOpenPositions_.contains(key), scenario.name + QStringLiteral(": completed allocation removed"));
            } else {
                check(window.dashboardRuntimeOpenPositions_.contains(key), scenario.name + QStringLiteral(": residual allocation retained"));
                const auto residual = window.dashboardRuntimeOpenPositions_.value(key);
                check(residual.quantity == remaining && residual.entryPrice == 100.0 && residual.leverage == 2.0,
                      scenario.name + QStringLiteral(": preserve owned cost basis and subtract only confirmed execution"));
                check(residual.displayMarginUsdt == 100.0 * remaining / 2.0
                          && residual.roiBasisUsdt == 80.0 * remaining / 2.0,
                      scenario.name + QStringLiteral(": residual margins must be allocation-relative, even without a table row"));
            }
            if (scenario.shared) {
                if (scenario.fill == 2.0) {
                    check(!window.dashboardRuntimeOpenPositions_.contains(otherKey)
                              && liveRemaining == 0.0 && snapshots == 2,
                          scenario.name + QStringLiteral(": successive closes consume each allocation once with a fresh snapshot"));
                    check(table->item(3, 16)->data(Qt::UserRole).toString() == QStringLiteral("CLOSED"),
                          scenario.name + QStringLiteral(": the second allocation closes its own row"));
                } else {
                    const auto other = window.dashboardRuntimeOpenPositions_.value(otherKey);
                    check(other.quantity == 3.0 && other.displayMarginUsdt == 150.0 && other.roiBasisUsdt == 120.0,
                          scenario.name + QStringLiteral(": first partial result cannot alter or submit the next allocation"));
                    check(table->item(3, 16)->data(Qt::UserRole).toString() == QStringLiteral("OPEN")
                              && table->item(3, 6)->data(Qt::UserRole + 2).toDouble() == 3.0,
                          scenario.name + QStringLiteral(": the unattempted allocation remains visible"));
                }
            }
            if (scenario.visible) {
                check(table->item(0, 16)->data(Qt::UserRole).toString()
                          == (remaining == 0.0 ? QStringLiteral("CLOSED") : QStringLiteral("OPEN")),
                      scenario.name + QStringLiteral(": only a completely executed allocation is marked closed"));
                if (remaining > 0.0) {
                    check(table->item(0, 6)->data(Qt::UserRole + 2).toDouble() == remaining,
                          scenario.name + QStringLiteral(": visible quantity matches remaining allocation"));
                }
                for (int row : {1, 2}) {
                    check(table->item(row, 16)->data(Qt::UserRole).toString() == QStringLiteral("OPEN")
                              && table->item(row, 6)->data(Qt::UserRole + 2).toDouble() == 3.0,
                          scenario.name + QStringLiteral(": other side and connector rows remain unchanged"));
                }
            }
            if (scenario.fill < requestQty && !scenario.snapshotFails) {
                check(window.dashboardOrderExecutionSession_.reconciliationRequired(),
                      scenario.name + QStringLiteral(": incomplete outcomes retain the uncertainty barrier"));
                if (window.dashboardOrderExecutionSession_.unresolvedOrder()) {
                    check(window.dashboardOrderExecutionSession_.unresolvedOrder()->confirmedExecutedQuantity(requestQty) == scenario.fill,
                          scenario.name + QStringLiteral(": retained evidence contains only the confirmed execution"));
                }
            }
        }
    }

    void check(bool condition, const QString &message) {
        if (!condition) {
            ++failures_;
            QTextStream(stderr) << "FAIL: " << message << '\n';
        }
    }

    static BinanceRestClient::FuturesOrderResult uncertain(bool partial) {
        BinanceRestClient::FuturesOrderResult result;
        result.clientOrderId = QStringLiteral("test-pending-order");
        result.reconciliationRequired = true;
        result.executionConfirmed = partial;
        result.executedQty = partial ? 0.25 : 0.0;
        result.status = partial ? QStringLiteral("CANCELED") : QString();
        return result;
    }

    static QPushButton *findButton(TradingBotWindow &window, bool all) {
        const QString text = all ? QStringLiteral("Market Close ALL Positions") : QStringLiteral("Market Close Selected");
        for (auto *button : window.findChildren<QPushButton *>()) {
            if (button->text() == text) return button;
        }
        return nullptr;
    }

    static void setCombo(QComboBox *combo, const QString &text) {
        QSignalBlocker block(combo);
        int index = combo->findText(text);
        if (index < 0) {
            combo->addItem(text);
            index = combo->count() - 1;
        }
        combo->setCurrentIndex(index);
    }

    static void configure(TradingBotWindow &window, bool futures) {
        setCombo(window.dashboardModeCombo_, QStringLiteral("Demo/Testnet"));
        setCombo(window.dashboardAccountTypeCombo_, futures ? QStringLiteral("Futures") : QStringLiteral("Spot"));
        setCombo(window.dashboardExchangeCombo_, QStringLiteral("Binance"));
        window.dashboardApiKey_->setText(QStringLiteral("fixture-key-not-a-credential"));
        window.dashboardApiSecret_->setText(QStringLiteral("fixture-secret-not-a-credential"));
        window.positionsCumulativeView_ = false;
        auto *table = window.positionsTable_;
        table->setSortingEnabled(false);
        table->setRowCount(1);
        for (int col = 0; col < table->columnCount(); ++col) table->setItem(0, col, new QTableWidgetItem());
        for (const auto &cell : QList<QPair<int, QString>>{{0, QStringLiteral("BTCUSDT")},
                 {6, QStringLiteral("1")}, {8, QStringLiteral("1m")},
                 {12, QStringLiteral("LONG")}, {16, QStringLiteral("OPEN")}}) {
            table->item(0, cell.first)->setText(cell.second);
            table->item(0, cell.first)->setData(Qt::UserRole, cell.second);
        }
        table->item(0, 6)->setData(Qt::UserRole + 2, 1.0);
        table->selectRow(0);
        table->setCurrentCell(0, 0);
        table->setRowHidden(0, false);
        TradingBotWindow::RuntimePosition position;
        position.side = QStringLiteral("LONG");
        position.interval = QStringLiteral("1m");
        position.quantity = 1.0;
        window.dashboardRuntimeOpenPositions_.insert(QStringLiteral("BTCUSDT|1m|LONG"), position);
    }
};

int main(int argc, char **argv) {
    QTemporaryDir home;
    if (!home.isValid()) return 2;
    qputenv("HOME", home.path().toUtf8());
    qputenv("USERPROFILE", home.path().toUtf8());
    qputenv("XDG_CONFIG_HOME", home.path().toUtf8());
    qputenv("BOT_DESKTOP_SERVICE_API_AUTOSTART", QByteArray("0"));
    qputenv("BOT_SERVICE_API_TOKEN", QByteArray("fixture-token-not-a-credential"));
    qputenv("QT_QPA_PLATFORM", QByteArray("offscreen"));
    QStandardPaths::setTestModeEnabled(true);
    QDir::setCurrent(home.path());
    QApplication app(argc, argv);
    app.setProperty("tradingBotBoundedSmoke", true);
    NativePositionCloseTests tests;
    return tests.run(app.arguments().contains(QStringLiteral("--stop-accounting-only")));
}
