#pragma once

#include <QMainWindow>
#include <QMap>
#include <QSet>
#include <QVariantMap>
#include <chrono>

class QListWidget;
class QLabel;
class QPushButton;
class QLineEdit;
class QComboBox;
class QCheckBox;
class QTableWidget;
class QDoubleSpinBox;
class QSpinBox;
class QDateEdit;
class QTimer;
class QTabWidget;
class QWidget;
class QTextEdit;

class BacktestWindow final : public QMainWindow {
    Q_OBJECT

public:
    explicit BacktestWindow(QWidget *parent = nullptr);

private slots:
    void handleAddCustomIntervals();
    void handleRunBacktest();
    void handleStopBacktest();
    void updateBotActiveTime();
    void applyDashboardTheme(const QString &themeName);

private:
    QWidget *createMarketsGroup();
    QWidget *createParametersGroup();
    QWidget *createIndicatorsGroup();
    QWidget *createResultsGroup();
    QWidget *createDashboardTab();
    QWidget *createChartTab();
    QWidget *createPositionsTab();
    QWidget *createBacktestTab();
    QWidget *createCodeTab();
    QWidget *createPlaceholderTab(const QString &title, const QString &body);
    void populateDefaults();
    void showIndicatorDialog(const QString &indicatorName);
    void refreshDashboardBalance();
    void refreshDashboardSymbols();
    void applyDashboardTemplate(const QString &templateKey);
    void startDashboardRuntime();
    void stopDashboardRuntime();
    void runDashboardRuntimeCycle();
    void appendDashboardAllLog(const QString &message);
    void appendDashboardPositionLog(const QString &message);
    void appendDashboardWaitingLog(const QString &message);
    void wireSignals();
    void ensureBotTimer(bool running);
    void updateStatusMessage(const QString &message);
    void appendUniqueInterval(const QString &interval);

    QListWidget *symbolList_;
    QListWidget *intervalList_;
    QLineEdit *customIntervalEdit_;
    QLabel *statusLabel_;
    QLabel *botStatusLabel_;
    QLabel *botTimeLabel_;
    QPushButton *runButton_;
    QPushButton *stopButton_;
    QPushButton *addSelectedBtn_;
    QPushButton *addAllBtn_;
    QComboBox *symbolSourceCombo_;
    QTableWidget *resultsTable_;
    QTimer *botTimer_;
    std::chrono::steady_clock::time_point botStart_;
    QTabWidget *tabs_;
    QWidget *backtestTab_;
    QComboBox *dashboardThemeCombo_;
    QWidget *dashboardPage_;
    QWidget *codePage_;
    QLineEdit *dashboardApiKey_;
    QLineEdit *dashboardApiSecret_;
    QLabel *dashboardBalanceLabel_;
    QPushButton *dashboardRefreshBtn_;
    QComboBox *dashboardAccountTypeCombo_;
    QComboBox *dashboardModeCombo_;
    QComboBox *dashboardConnectorCombo_;
    QComboBox *dashboardExchangeCombo_;
    QComboBox *dashboardIndicatorSourceCombo_;
    QComboBox *dashboardTemplateCombo_;
    QComboBox *dashboardMarginModeCombo_;
    QDoubleSpinBox *dashboardPositionPctSpin_;
    QSpinBox *dashboardLeverageSpin_;
    QListWidget *dashboardSymbolList_;
    QListWidget *dashboardIntervalList_;
    QPushButton *dashboardRefreshSymbolsBtn_;
    QMap<QString, QCheckBox *> dashboardIndicatorChecks_;
    QMap<QString, QPushButton *> dashboardIndicatorButtons_;
    QMap<QString, QVariantMap> dashboardIndicatorParams_;
    QPushButton *dashboardStartBtn_;
    QPushButton *dashboardStopBtn_;
    QTableWidget *dashboardOverridesTable_;
    QTextEdit *dashboardAllLogsEdit_;
    QTextEdit *dashboardPositionLogsEdit_;
    QTextEdit *dashboardWaitingLogsEdit_;
    QTimer *dashboardRuntimeTimer_;
    QMap<QString, qint64> dashboardRuntimeLastEvalMs_;
    QSet<QString> dashboardRuntimeConnectorWarnings_;
    struct RuntimePosition {
        QString side;
        QString interval;
        double entryPrice = 0.0;
        double quantity = 0.0;
        double leverage = 1.0;
    };
    QMap<QString, RuntimePosition> dashboardRuntimeOpenPositions_;

    QComboBox *chartMarketCombo_;
    QComboBox *chartSymbolCombo_;
    QComboBox *chartIntervalCombo_;
    QComboBox *chartViewModeCombo_;
    QCheckBox *chartAutoFollowCheck_;
    QLabel *chartPnlActiveLabel_;
    QLabel *chartPnlClosedLabel_;
    QLabel *chartBotStatusLabel_;
    QLabel *chartBotTimeLabel_;
    QTableWidget *positionsTable_;
};
