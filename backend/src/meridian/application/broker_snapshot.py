"""Broker-reported snapshot projection: no reconstructed totals or ledger math."""

from meridian.adapters.broker_evidence import BrokerEvidence, number


def _amount(value):
    if value is None:
        return None
    decimal = number(value)
    if decimal == 0:
        return "0"
    result = format(decimal, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def broker_snapshot(evidence: BrokerEvidence) -> dict:
    observations = evidence.document["observations"]
    summary = observations["account_summary"]["records"][0]
    investments = summary["investments"]
    cash = summary.get("cash", {})
    positions = []
    for row in observations["positions"]["records"]:
        instrument = row["instrument"]
        wallet = row.get("walletImpact") or {}
        positions.append(
            {
                "ticker": instrument["ticker"],
                "name": instrument.get("name"),
                "instrument_currency": instrument.get("currency"),
                "quantity": _amount(row["quantity"]),
                "current_price": _amount(row.get("currentPrice")),
                "average_price_paid": _amount(row.get("averagePricePaid")),
                "account_currency": wallet.get("currency"),
                "current_value": _amount(wallet.get("currentValue")),
                "total_cost": _amount(wallet.get("totalCost")),
                "unrealized_profit_loss": _amount(wallet.get("unrealizedProfitLoss")),
                "fx_impact": _amount(wallet.get("fxImpact")),
            }
        )
    return {
        "source": "trading212",
        "basis": "broker_reported",
        "environment": evidence.environment,
        "currency": summary["currency"],
        "total_value": _amount(summary["totalValue"]),
        "investments": {
            key: _amount(investments.get(key))
            for key in ("currentValue", "totalCost", "realizedProfitLoss", "unrealizedProfitLoss")
        },
        # Preserve components independently: no unverified cash-additivity rule.
        "cash_components": {
            key: _amount(cash.get(key))
            for key in ("availableToTrade", "inPies", "reservedForOrders")
        },
        "positions": positions,
        "account_retrieval": {
            key: observations["account_summary"][key]
            for key in ("retrieval_started_at", "retrieval_completed_at")
        },
        "positions_retrieval": {
            key: observations["positions"][key]
            for key in ("retrieval_started_at", "retrieval_completed_at")
        },
        "quote_timestamp": None,
        "quote_age": "unknown",
        "history_coverage": "unverified",
        "historical_returns": None,
        "profit_loss_basis": "broker_reported_management_not_tax",
        "snapshot_atomicity": "separate_provider_requests",
    }
