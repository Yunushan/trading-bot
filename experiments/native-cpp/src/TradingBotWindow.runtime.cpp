#include "TradingBotWindow.h"

#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QTimer>

#include <algorithm>
#include <chrono>

namespace {

QString formatDuration(qint64 seconds) {
    seconds = std::max<qint64>(0, seconds);

    constexpr qint64 kMinute = 60;
    constexpr qint64 kHour = 60 * kMinute;
    constexpr qint64 kDay = 24 * kHour;
    constexpr qint64 kMonth = 30 * kDay;

    const qint64 months = seconds / kMonth;
    seconds %= kMonth;
    const qint64 days = seconds / kDay;
    seconds %= kDay;
    const qint64 hours = seconds / kHour;
    seconds %= kHour;
    const qint64 minutes = seconds / kMinute;
    seconds %= kMinute;

    QStringList parts;
    if (months > 0) {
        parts.append(QStringLiteral("%1mo").arg(months));
    }
    if (!parts.isEmpty() || days > 0) {
        parts.append(QStringLiteral("%1d").arg(days));
    }
    if (!parts.isEmpty() || hours > 0) {
        parts.append(QStringLiteral("%1h").arg(hours));
    }
    if (!parts.isEmpty() || minutes > 0) {
        parts.append(QStringLiteral("%1m").arg(minutes));
    }
    parts.append(QStringLiteral("%1s").arg(seconds));
    return parts.join(QStringLiteral(" "));
}

} // namespace

void TradingBotWindow::handleAddCustomIntervals() {
    if (!intervalList_) {
        return;
    }
    const QString raw = customIntervalEdit_ ? customIntervalEdit_->text().trimmed() : QString();
    if (raw.isEmpty()) {
        updateStatusMessage("No intervals entered.");
        return;
    }
    const auto parts = raw.split(',', Qt::SkipEmptyParts);
    for (QString part : parts) {
        part = part.trimmed();
        appendUniqueInterval(part);
    }
    if (customIntervalEdit_) {
        customIntervalEdit_->clear();
    }
    updateStatusMessage("Custom intervals appended.");
}

void TradingBotWindow::updateBotActiveTime() {
    if (!botTimer_) {
        return;
    }
    const auto now = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - botStart_);
    const QString text = "Bot Active Time: " + formatDuration(elapsed.count());
    if (botTimeLabel_) {
        botTimeLabel_->setText(text);
    }
    if (chartBotTimeLabel_) {
        chartBotTimeLabel_->setText(text);
    }
    if (positionsBotTimeLabel_) {
        positionsBotTimeLabel_->setText(text);
    }
    if (codeBotTimeLabel_) {
        codeBotTimeLabel_->setText(text);
    }
    if (dashboardRuntimeActive_ && dashboardBotTimeLabel_) {
        dashboardBotTimeLabel_->setText(formatDuration(elapsed.count()));
    }
    refreshPositionsSummaryLabels();
}

void TradingBotWindow::ensureBotTimer(bool running) {
    if (!botTimer_) {
        botTimer_ = new QTimer(this);
        botTimer_->setInterval(1000);
        connect(botTimer_, &QTimer::timeout, this, &TradingBotWindow::updateBotActiveTime);
    }
    if (running) {
        botTimer_->start();
    } else {
        botTimer_->stop();
    }
}

void TradingBotWindow::updateStatusMessage(const QString &message) {
    if (statusLabel_) {
        statusLabel_->setText(message);
    }
}

void TradingBotWindow::appendUniqueInterval(const QString &interval) {
    if (!intervalList_ || interval.isEmpty()) {
        return;
    }
    for (int i = 0; i < intervalList_->count(); ++i) {
        if (intervalList_->item(i)->text().compare(interval, Qt::CaseInsensitive) == 0) {
            return;
        }
    }
    intervalList_->addItem(interval);
}
