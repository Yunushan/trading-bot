#pragma once

#include "BinanceRestClient.h"

#include <optional>
#include <utility>

// UI-thread session containment only. Durable intent recovery is still required
// before the experimental native exchange runtime can be promoted.
class NativeOrderExecutionSession final {
public:
    using Result = BinanceRestClient::FuturesOrderResult;

    NativeOrderExecutionSession() = default;
    NativeOrderExecutionSession(const NativeOrderExecutionSession &) = delete;
    NativeOrderExecutionSession &operator=(const NativeOrderExecutionSession &) = delete;

    bool submissionBlocked() const { return inFlight_ || unresolved_.has_value(); }
    bool reconciliationRequired() const { return unresolved_.has_value(); }
    const std::optional<Result> &unresolvedOrder() const { return unresolved_; }
    double unresolvedRequestedQuantity() const { return unresolvedRequestedQuantity_; }

    template <typename Submit>
    Result submit(double requestedQuantity, Submit &&submitOrder) {
        if (submissionBlocked()) {
            Result blocked;
            blocked.reconciliationRequired = true;
            blocked.error = QStringLiteral("Native order submission blocked: an earlier order is in flight or requires reconciliation.");
            // Never return a previous fill as the result of a blocked request.
            return blocked;
        }
        if (!qIsFinite(requestedQuantity) || requestedQuantity <= 0.0) {
            Result invalid;
            invalid.error = QStringLiteral("Order quantity must be finite and positive.");
            return invalid;
        }
        inFlight_ = true;
        Result result;
        try {
            result = std::forward<Submit>(submitOrder)();
        } catch (...) {
            result.reconciliationRequired = true;
            result.error = QStringLiteral("Native submission interrupted without a confirmed outcome; reconciliation required.");
            unresolved_ = result;
            unresolvedRequestedQuantity_ = requestedQuantity;
            inFlight_ = false;
            throw;
        }
        inFlight_ = false;
        if (!result.hasConfirmedFill(requestedQuantity)
            && (result.reconciliationRequired || result.executionConfirmed
                || result.ok || !result.clientOrderId.isEmpty())) {
            result.ok = false;
            result.reconciliationRequired = true;
            unresolved_ = result;
            unresolvedRequestedQuantity_ = requestedQuantity;
        }
        return result;
    }

private:
    bool inFlight_ = false;
    std::optional<Result> unresolved_;
    double unresolvedRequestedQuantity_ = 0.0;
};
