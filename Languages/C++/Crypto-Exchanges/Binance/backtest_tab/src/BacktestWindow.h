#pragma once

#include <QMainWindow>
#include <chrono>

class QListWidget;
class QLabel;
class QPushButton;
class QLineEdit;
class QComboBox;
class QTableWidget;
class QDoubleSpinBox;
class QSpinBox;
class QDateEdit;
class QTimer;
class QTabWidget;

class BacktestWindow final : public QMainWindow {
    Q_OBJECT

public:
    explicit BacktestWindow(QWidget *parent = nullptr);

private slots:
    void handleAddCustomIntervals();
    void handleRunBacktest();
    void handleStopBacktest();
    void updateBotActiveTime();

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
    void launchPythonBot();
    void populateDefaults();
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
};
