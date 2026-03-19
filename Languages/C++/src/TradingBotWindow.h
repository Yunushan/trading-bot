#pragma once

#include "BinanceRestClient.h"

#include <QMainWindow>
#include <QList>
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
class QVBoxLayout;
class BinanceWsClient;

// Main Qt window for the C++ desktop runtime.
//
// Design intent:
// - Mirror core Python dashboard/backtest interactions.
// - Keep UI state explicit via typed members for cross-tab synchronization.
// - Host lightweight runtime simulation hooks (logs, queue state, position table).
class TradingBotWindow final : public QMainWindow {
    Q_OBJECT

public:
    explicit TradingBotWindow(QWidget *parent = nullptr);

private slots:
    void handleAddCustomIntervals();
    void handleRunBacktest();
    void handleStopBacktest();
    void updateBotActiveTime();
    void applyDashboardTheme(const QString &themeName);

private:
    // Tab/page creation helpers.
    QWidget *createMarketsGroup();
    QWidget *createParametersGroup();
    QWidget *createIndicatorsGroup();
    QWidget *createResultsGroup();
    QWidget *createDashboardTab();
    QWidget *createChartTab();
    QWidget *createPositionsTab();
    QWidget *createBacktestTab();
    QWidget *createLiquidationHeatmapTab();
    QWidget *createLiquidationWebPanel(const QString &title, const QString &url, const QString &note = QString());
    QWidget *createCodeTab();
    QWidget *createPlaceholderTab(const QString &title, const QString &body);
    // Runtime/data flow helpers.
    void populateDefaults();
    void showIndicatorDialog(const QString &indicatorName);
    void refreshDashboardBalance();
    void refreshDashboardSymbols();
    void refreshBacktestSymbols();
    void applyDashboardTemplate(const QString &templateKey);
    void addSelectedBacktestSymbolIntervalPairs();
    void removeSelectedBacktestSymbolIntervalPairs();
    void clearBacktestSymbolIntervalPairs();
    void refreshBacktestSymbolIntervalTable();
    void startDashboardRuntime();
    void stopDashboardRuntime();
    void runDashboardRuntimeCycle();
    void appendDashboardAllLog(const QString &message);
    void appendDashboardPositionLog(const QString &message);
    void appendDashboardWaitingLog(const QString &message);
    void refreshDashboardWaitingQueueTable();
    void addSelectedDashboardOverrideRows();
    void removeSelectedDashboardOverrideRows();
    void clearDashboardOverrideRows();
    void saveDashboardConfig();
    void loadDashboardConfig();
    // Utility/UI state helpers.
    void wireSignals();
    void ensureBotTimer(bool running);
    void updateStatusMessage(const QString &message);
    double currentDashboardPaperBalanceUsdt() const;
    void syncDashboardPaperBalanceUi();
    void appendUniqueInterval(const QString &interval);
    void refreshPositionsTableSizing(bool resizeColumns = true, bool resizeRows = true);
    void updateDashboardStopLossWidgetState();
    void setDashboardRuntimeControlsEnabled(bool enabled);
    void applyPositionsViewMode(bool resizeColumns = true, bool resizeRows = true);
    void refreshPositionsSummaryLabels();
    bool openExternalUrl(const QString &url);
    void registerDashboardRuntimeLockWidget(QWidget *widget);
    QString dashboardEnabledIndicatorsSummary() const;
    QString dashboardStopLossSummary() const;
    QString dashboardStrategySummary() const;
    bool dashboardOverridesHasPair(const QString &symbol, const QString &interval) const;
    bool addDashboardOverrideRow(const QString &symbolRaw, const QString &intervalRaw);

    void createDashboardAccountStatusSection(QWidget *page, QVBoxLayout *root);
    void createDashboardExchangeAndMarketsSections(QWidget *page, QVBoxLayout *root);
    void createDashboardStrategySection(QWidget *page, QVBoxLayout *root);
    void createDashboardRuntimeSection(QWidget *page, QVBoxLayout *root);

    QListWidget *symbolList_;
    QListWidget *intervalList_;
    QLineEdit *customIntervalEdit_;
    QLabel *statusLabel_;
    QLabel *botStatusLabel_;
    QLabel *botTimeLabel_;
    QLabel *backtestPnlActiveLabel_;
    QLabel *backtestPnlClosedLabel_;
    QPushButton *runButton_;
    QPushButton *stopButton_;
    QPushButton *addSelectedBtn_;
    QPushButton *addAllBtn_;
    QComboBox *symbolSourceCombo_;
    QPushButton *backtestRefreshSymbolsBtn_;
    QTableWidget *backtestSymbolIntervalTable_;
    QComboBox *backtestConnectorCombo_;
    QComboBox *backtestLoopCombo_;
    QSpinBox *backtestLeverageSpin_;
    QCheckBox *backtestStopLossEnableCheck_;
    QComboBox *backtestStopLossModeCombo_;
    QComboBox *backtestStopLossScopeCombo_;
    QComboBox *backtestSideCombo_;
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
    QLabel *dashboardPaperBalanceTitleLabel_;
    QDoubleSpinBox *dashboardPaperBalanceSpin_;
    QLabel *dashboardPnlActiveLabel_;
    QLabel *dashboardPnlClosedLabel_;
    QLabel *dashboardBotStatusLabel_;
    QLabel *dashboardBotTimeLabel_;
    QLabel *codePnlActiveLabel_;
    QLabel *codePnlClosedLabel_;
    QLabel *codeBotStatusLabel_;
    QLabel *codeBotTimeLabel_;
    QPushButton *dashboardRefreshBtn_;
    QComboBox *dashboardAccountTypeCombo_;
    QComboBox *dashboardModeCombo_;
    QComboBox *dashboardConnectorCombo_;
    QComboBox *dashboardExchangeCombo_;
    QComboBox *dashboardIndicatorSourceCombo_;
    QComboBox *dashboardSignalFeedCombo_;
    QComboBox *dashboardTemplateCombo_;
    QComboBox *dashboardMarginModeCombo_;
    QComboBox *dashboardPositionModeCombo_;
    QComboBox *dashboardSideCombo_ = nullptr;
    QComboBox *dashboardLoopOverrideCombo_ = nullptr;
    QDoubleSpinBox *dashboardPositionPctSpin_;
    QSpinBox *dashboardLeverageSpin_;
    QListWidget *dashboardSymbolList_;
    QListWidget *dashboardIntervalList_;
    QPushButton *dashboardRefreshSymbolsBtn_;
    QMap<QString, QCheckBox *> dashboardIndicatorChecks_;
    QMap<QString, QPushButton *> dashboardIndicatorButtons_;
    QMap<QString, QVariantMap> dashboardIndicatorParams_;
    QPushButton *dashboardAddSelectedOverrideBtn_ = nullptr;
    QPushButton *dashboardRemoveSelectedOverrideBtn_ = nullptr;
    QPushButton *dashboardClearOverridesBtn_ = nullptr;
    QPushButton *dashboardStartBtn_;
    QPushButton *dashboardStopBtn_;
    QPushButton *dashboardSaveConfigBtn_ = nullptr;
    QPushButton *dashboardLoadConfigBtn_ = nullptr;
    QTableWidget *dashboardOverridesTable_;
    QTextEdit *dashboardAllLogsEdit_;
    QTextEdit *dashboardPositionLogsEdit_;
    QTextEdit *dashboardWaitingLogsEdit_;
    QTableWidget *dashboardWaitingQueueTable_;
    QTimer *dashboardRuntimeTimer_;
    QMap<QString, qint64> dashboardRuntimeLastEvalMs_;
    QMap<QString, qint64> dashboardRuntimeEntryRetryAfterMs_;
    QMap<QString, double> dashboardRuntimeOpenQtyCaps_;
    QSet<QString> dashboardRuntimeConnectorWarnings_;
    QSet<QString> dashboardRuntimeIntervalWarnings_;
    QMap<QString, BinanceWsClient *> dashboardRuntimeSignalSockets_;
    QMap<QString, QVector<BinanceRestClient::KlineCandle>> dashboardRuntimeSignalCandles_;
    QMap<QString, bool> dashboardRuntimeSignalLastClosed_;
    QMap<QString, qint64> dashboardRuntimeSignalUpdateMs_;
    QList<QWidget *> dashboardRuntimeLockWidgets_;
    QCheckBox *dashboardLeadTraderEnableCheck_;
    QComboBox *dashboardLeadTraderCombo_;
    QCheckBox *dashboardStopWithoutCloseCheck_;
    QCheckBox *dashboardLiveIndicatorValuesCheck_ = nullptr;
    QCheckBox *dashboardOneWayCheck_ = nullptr;
    QCheckBox *dashboardHedgeStackCheck_ = nullptr;
    QCheckBox *dashboardStopLossEnableCheck_;
    QComboBox *dashboardStopLossModeCombo_;
    QComboBox *dashboardStopLossScopeCombo_;
    QDoubleSpinBox *dashboardStopLossUsdtSpin_;
    QDoubleSpinBox *dashboardStopLossPercentSpin_;
    bool dashboardRuntimeActive_ = false;
    bool dashboardRuntimeStopping_ = false;
    bool dashboardRuntimeCycleInProgress_ = false;
    QMap<QString, QVariantMap> dashboardWaitingActiveEntries_;
    QList<QVariantMap> dashboardWaitingHistoryEntries_;
    int dashboardWaitingHistoryMax_ = 500;
    struct RuntimePosition {
        QString side;
        QString interval;
        QString signalSource;
        QString connectorKey;
        QString connectorBaseUrl;
        double entryPrice = 0.0;
        double quantity = 0.0;
        double leverage = 1.0;
        double roiBasisUsdt = 0.0;
        double displayMarginUsdt = 0.0;
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
    QLabel *positionsPnlActiveLabel_;
    QLabel *positionsPnlClosedLabel_;
    QLabel *positionsTotalBalanceLabel_;
    QLabel *positionsAvailableBalanceLabel_;
    QLabel *positionsBotStatusLabel_;
    QLabel *positionsBotTimeLabel_;
    double positionsLastTotalBalanceUsdt_;
    double positionsLastAvailableBalanceUsdt_;
    QComboBox *positionsViewCombo_;
    bool positionsCumulativeView_ = false;
    QTableWidget *positionsTable_;
    QCheckBox *positionsAutoRowHeightCheck_;
    QCheckBox *positionsAutoColumnWidthCheck_;
    qint64 positionsRowSequenceCounter_ = 1;
};

