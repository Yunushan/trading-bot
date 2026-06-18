#include "../src/TradingBotWindowSupport.h"

#include <QByteArray>
#include <QCoreApplication>
#include <QHostAddress>
#include <QJsonObject>
#include <QTcpServer>
#include <QTcpSocket>

#include <iostream>

namespace {

bool contains(const QStringList &values, const QString &expected) {
    return values.contains(expected);
}

} // namespace

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    int failures = 0;
    const auto check = [&failures](bool condition, const QString &message) {
        if (!condition) {
            std::cerr << message.toStdString() << '\n';
            ++failures;
        }
    };

    const QStringList routes = TradingBotWindowSupport::pythonSourceServiceRouteNames();
    check(contains(routes, QStringLiteral("dashboard")),
          QStringLiteral("generated route names should include dashboard"));
    check(contains(routes, QStringLiteral("config")),
          QStringLiteral("generated route names should include config"));
    check(contains(routes, QStringLiteral("control_start")),
          QStringLiteral("generated route names should include control_start"));

    const QStringList configMethods =
        TradingBotWindowSupport::pythonSourceServiceRouteMethods(QStringLiteral("config"));
    check(contains(configMethods, QStringLiteral("GET")),
          QStringLiteral("config route should declare GET"));
    check(contains(configMethods, QStringLiteral("PUT")),
          QStringLiteral("config route should declare PUT"));
    check(contains(configMethods, QStringLiteral("PATCH")),
          QStringLiteral("config route should declare PATCH"));

    const QStringList dashboardQueryFields =
        TradingBotWindowSupport::pythonSourceServiceRouteQueryFields(QStringLiteral("dashboard"));
    check(contains(dashboardQueryFields, QStringLiteral("log_limit")),
          QStringLiteral("dashboard route should expose log_limit query field"));
    check(contains(dashboardQueryFields, QStringLiteral("incident_limit")),
          QStringLiteral("dashboard route should expose incident_limit query field"));

    const QStringList configRequestFields =
        TradingBotWindowSupport::pythonSourceServiceRouteRequestFields(QStringLiteral("config"));
    check(contains(configRequestFields, QStringLiteral("config")),
          QStringLiteral("config route should expose config request field"));

    const QStringList controlStartRequestFields =
        TradingBotWindowSupport::pythonSourceServiceRouteRequestFields(QStringLiteral("control_start"));
    check(contains(controlStartRequestFields, QStringLiteral("requested_job_count")),
          QStringLiteral("control_start route should expose requested_job_count request field"));

    const QStringList dashboardResponseFields =
        TradingBotWindowSupport::pythonSourceServiceRouteResponseFields(QStringLiteral("dashboard"));
    check(contains(dashboardResponseFields, QStringLiteral("runtime")),
          QStringLiteral("dashboard route should expose runtime response field"));
    check(contains(dashboardResponseFields, QStringLiteral("service_api")),
          QStringLiteral("dashboard route should expose service_api response field"));

    const QStringList configResponseFields =
        TradingBotWindowSupport::pythonSourceServiceRouteResponseFields(QStringLiteral("config"));
    check(contains(configResponseFields, QStringLiteral("llm")),
          QStringLiteral("config route should expose llm response field"));
    check(contains(configResponseFields, QStringLiteral("exchange_support")),
          QStringLiteral("config route should expose exchange_support response field"));

    QTcpServer server;
    check(server.listen(QHostAddress::LocalHost, 0),
          QStringLiteral("local HTTP test server should listen"));
    QByteArray observedRequest;
    QObject::connect(&server, &QTcpServer::newConnection, [&server, &observedRequest]() {
        QTcpSocket *socket = server.nextPendingConnection();
        QObject::connect(socket, &QTcpSocket::readyRead, [socket, &observedRequest]() {
            observedRequest += socket->readAll();
            if (!observedRequest.contains("\r\n\r\n")) {
                return;
            }
            const QByteArray body =
                R"({"runtime":{"service_name":"Trading Bot Service"},"service_api":{"host_context":"cpp-test"}})";
            QByteArray response =
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                "Connection: close\r\n"
                "Content-Length: ";
            response += QByteArray::number(body.size());
            response += "\r\n\r\n";
            response += body;
            socket->write(response);
            socket->flush();
            socket->disconnectFromHost();
        });
    });

    qputenv("BOT_DESKTOP_SERVICE_API_BASE_URL",
            QByteArray("http://127.0.0.1:") + QByteArray::number(server.serverPort()) + QByteArray("/"));

    const TradingBotWindowSupport::ServiceApiJsonResult apiResult =
        TradingBotWindowSupport::serviceApiRequestJson(QStringLiteral("GET"), QStringLiteral("dashboard"), {}, 5000);
    check(apiResult.ok, QStringLiteral("C++ Service API helper should parse local JSON response"));
    check(apiResult.statusCode == 200,
          QStringLiteral("C++ Service API helper should expose HTTP status"));
    check(
        apiResult.document.object().value(QStringLiteral("runtime")).toObject().value(QStringLiteral("service_name")).toString()
            == QStringLiteral("Trading Bot Service"),
        QStringLiteral("C++ Service API helper should expose parsed runtime response body"));
    check(observedRequest.startsWith("GET /api/v1/dashboard "),
          QStringLiteral("C++ Service API helper should request generated dashboard route path"));

    QTcpServer terminalServer;
    check(terminalServer.listen(QHostAddress::LocalHost, 0),
          QStringLiteral("local terminal HTTP test server should listen"));
    QByteArray observedTerminalRequest;
    QObject::connect(&terminalServer, &QTcpServer::newConnection, [&terminalServer, &observedTerminalRequest]() {
        QTcpSocket *socket = terminalServer.nextPendingConnection();
        QObject::connect(socket, &QTcpSocket::readyRead, [socket, &observedTerminalRequest]() {
            observedTerminalRequest += socket->readAll();
            if (!observedTerminalRequest.contains("\r\n\r\n")) {
                return;
            }
            const QByteArray body =
                R"({"command":"status api_key=<redacted>","exit_code":0,"output":"{\"state\":\"ready\"}","source":"cpp-test","created_at":"2026-06-18T12:10:00+00:00","command_type":"service-command"})";
            QByteArray response =
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                "Connection: close\r\n"
                "Content-Length: ";
            response += QByteArray::number(body.size());
            response += "\r\n\r\n";
            response += body;
            socket->write(response);
            socket->flush();
            socket->disconnectFromHost();
        });
    });

    qputenv("BOT_DESKTOP_SERVICE_API_BASE_URL",
            QByteArray("http://127.0.0.1:") + QByteArray::number(terminalServer.serverPort()));
    const TradingBotWindowSupport::ServiceApiJsonResult terminalResult =
        TradingBotWindowSupport::serviceApiRequestJson(
            QStringLiteral("POST"),
            QStringLiteral("terminal_run"),
            QJsonObject{
                {QStringLiteral("command"), QStringLiteral("status api_key=super-secret-value")},
                {QStringLiteral("source"), QStringLiteral("cpp-test")},
            },
            5000);
    check(terminalResult.ok,
          QStringLiteral("C++ Service API helper should parse terminal_run JSON response"));
    check(observedTerminalRequest.startsWith("POST /api/v1/terminal/run "),
          QStringLiteral("C++ Service API helper should request generated terminal_run route path"));
    check(observedTerminalRequest.contains("\"command\""),
          QStringLiteral("C++ Service API helper should send terminal command payload"));
    check(
        terminalResult.document.object().value(QStringLiteral("command")).toString().contains(QStringLiteral("<redacted>")),
        QStringLiteral("terminal_run response should preserve Python redaction marker"));

    qputenv("BOT_DESKTOP_SERVICE_API_BASE_URL", QByteArray("http://127.0.0.1:8123/"));

    check(
        TradingBotWindowSupport::serviceApiUrlForRoute(QStringLiteral("dashboard"))
            == QStringLiteral("http://127.0.0.1:8123/api/v1/dashboard"),
        QStringLiteral("dashboard route URL should be generated from Python route path"));
    check(TradingBotWindowSupport::pythonSourceServiceRouteRequestFields(QStringLiteral("unknown")).isEmpty(),
          QStringLiteral("unknown route request fields should be empty"));
    check(
        TradingBotWindowSupport::serviceApiUrlForRoute(QStringLiteral("unknown"))
            == QStringLiteral("http://127.0.0.1:8123"),
        QStringLiteral("unknown route URL should return base Service API URL"));

    return failures == 0 ? 0 : 1;
}
