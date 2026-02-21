#pragma once

#include <QMainWindow>
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
    QComboBox *dashboardExchangeCombo_;
    QComboBox *dashboardIndicatorSourceCombo_;
    QListWidget *dashboardSymbolList_;
    QListWidget *dashboardIntervalList_;
    QPushButton *dashboardRefreshSymbolsBtn_;

    QComboBox *chartMarketCombo_;
    QComboBox *chartSymbolCombo_;
    QComboBox *chartIntervalCombo_;
    QComboBox *chartViewModeCombo_;
    QCheckBox *chartAutoFollowCheck_;
    QLabel *chartPnlActiveLabel_;
    QLabel *chartPnlClosedLabel_;
    QLabel *chartBotStatusLabel_;
    QLabel *chartBotTimeLabel_;
};
