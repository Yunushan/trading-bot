#pragma once

#include <QMap>
#include <QString>
#include <QVariantMap>
#include <QtGlobal>

class QTableWidget;
class QWidget;

namespace TradingBotWindowDashboardRuntimeDetail {

void setTableCellText(QTableWidget *table, int row, int col, const QString &text);

class ScopedTableSortingPause final {
public:
    explicit ScopedTableSortingPause(QTableWidget *table);
    ~ScopedTableSortingPause();

private:
    QTableWidget *table_ = nullptr;
    bool restoreSorting_ = false;
};

class ScopedTableUpdatesPause final {
public:
    explicit ScopedTableUpdatesPause(QTableWidget *table, bool enabled = true);
    ~ScopedTableUpdatesPause();

private:
    QTableWidget *table_ = nullptr;
    bool tableUpdatesWereEnabled_ = false;
    QWidget *viewport_ = nullptr;
    bool viewportUpdatesWereEnabled_ = false;
};

struct PositionTableActiveRowData {
    QString symbol;
    QString indicatorValueSummary;
    double sizeUsdt = 0.0;
    double quantity = 0.0;
    double markPrice = 0.0;
    double marginRatio = 0.0;
    double liqPrice = 0.0;
    double displayMarginUsdt = 0.0;
    double pnlUsdt = 0.0;
    double roiBasisUsdt = 0.0;
};

struct PositionTableOpenRowData {
    QString symbol;
    QString interval;
    QString triggerSource;
    QString triggerText;
    QString indicatorValueSummary;
    QString openSide;
    QString openedAtText;
    QString stopLossText;
    QString connectorKey;
    QString openOrderId;
    double sizeUsdt = 0.0;
    double quantity = 0.0;
    double markPrice = 0.0;
    double marginRatio = 0.0;
    double liqPrice = 0.0;
    double displayMarginUsdt = 0.0;
    double roiBasisUsdt = 0.0;
};

struct PositionTableCloseRowData {
    QString symbol;
    QString closedAtText;
    double closePrice = 0.0;
    double realizedPnlUsdt = 0.0;
    double realizedPnlPct = 0.0;
    double closeRoiBasisUsed = 0.0;
    bool partialClose = false;
    double remainingQty = 0.0;
    double remainingNotional = 0.0;
    double remainingDisplayMarginUsdt = 0.0;
    double remainingRoiBasisUsdt = 0.0;
};

struct IndicatorRuntimeSettings {
    double rsiBuyThreshold = 30.0;
    double rsiSellThreshold = 70.0;
    double stochBuyThreshold = 20.0;
    double stochSellThreshold = 80.0;
    double willrBuyThreshold = -80.0;
    double willrSellThreshold = -20.0;
    int rsiLength = 14;
    int stochLength = 14;
    int stochSmoothK = 3;
    int stochSmoothD = 3;
    int willrLength = 14;
};

struct IndicatorRuntimeValues {
    bool useRsi = false;
    bool useStochRsi = false;
    bool useWillr = false;
    bool rsiOk = false;
    bool stochRsiOk = false;
    bool willrOk = false;
    double rsi = 0.0;
    double stochRsi = 0.0;
    double willr = 0.0;
};

struct OpenSignalDecision {
    QString side;
    QString triggerText;
    QString triggerSource = QStringLiteral("rsi");

    bool hasSignal() const {
        return !side.isEmpty();
    }
};

QString tableCellRaw(const QTableWidget *table, int row, int col);
int findOpenPositionRow(const QTableWidget *table, const QString &symbol, const QString &interval, const QString &connectorKey);
void refreshActivePositionRow(QTableWidget *table, bool cumulativeView, int row, const PositionTableActiveRowData &data);
void setPositionIndicatorValueSummary(QTableWidget *table, bool cumulativeView, int row, const QString &indicatorValueSummary);
bool appendOpenPositionRow(QTableWidget *table, qint64 &rowSequenceCounter, const PositionTableOpenRowData &data);
void markPositionClosedRow(QTableWidget *table, bool cumulativeView, int row, const QString &closedAtText);
void applyCloseToPositionRow(QTableWidget *table, bool cumulativeView, int row, const PositionTableCloseRowData &data);
QString normalizedIndicatorSourceKey(const QString &sourceText);
QString runtimeKeyFor(const QString &symbol, const QString &interval, const QString &connectorToken = QString());
qint64 loopSecondsFromText(QString loopText);
qint64 intervalTokenToSeconds(QString intervalText);
QString intervalFloorToBinanceToken(qint64 seconds);
QString normalizeBinanceKlineInterval(QString intervalText, QString *warningOut = nullptr);
IndicatorRuntimeSettings buildIndicatorRuntimeSettings(const QMap<QString, QVariantMap> &indicatorParams);
QString formatIndicatorValueSummary(const IndicatorRuntimeValues &values);
QString formatIndicatorValueSummaryForSource(const IndicatorRuntimeValues &values, const QString &indicatorSource);
OpenSignalDecision determineOpenSignal(
    const IndicatorRuntimeValues &values,
    const IndicatorRuntimeSettings &settings,
    bool allowLong,
    bool allowShort);
bool shouldCloseBySource(
    const QString &source,
    bool isLong,
    const IndicatorRuntimeValues &values,
    const IndicatorRuntimeSettings &settings);

inline constexpr double kWaitingPositionLateThresholdSec = 45.0;

} // namespace TradingBotWindowDashboardRuntimeDetail
