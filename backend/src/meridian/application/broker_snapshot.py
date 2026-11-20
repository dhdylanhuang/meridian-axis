"""Broker-reported snapshot projection: no reconstructed totals or ledger math."""

import asyncio
import json

from meridian.adapters.broker_evidence import BrokerEvidence, canonical, instant, number


def _amount(value):
    if value is None:
        return None
    decimal = number(value)
    if decimal == 0:
        return "0"
    result = format(decimal, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def broker_snapshot(evidence: BrokerEvidence, *, metadata=None, previous=None) -> dict:
    observations = evidence.document["observations"]
    summary = observations["account_summary"]["records"][0]
    investments = summary["investments"]
    cash = summary.get("cash", {})
    positions = []
    metadata_payload = metadata["payload"] if metadata else {}
    listings = {row["ticker"]: row for row in metadata_payload.get("instruments", [])}
    observed_at = instant(observations["positions"]["retrieval_completed_at"])

    for row in observations["positions"]["records"]:
        instrument = row["instrument"]
        wallet = row.get("walletImpact") or {}
        listing = listings.get(instrument["ticker"], {})
        state = "pending"
        if instrument["ticker"] in metadata_payload.get("requested_tickers", []):
            state = "available" if listing else "missing"
            if (
                observed_at - instant(metadata_payload["retrieved_at"])
            ).total_seconds() > 36 * 3600:
                state = "stale"
        if listing.get("currencyCode") and instrument.get("currency") not in (
            None,
            listing["currencyCode"],
        ):
            state, listing = "conflict", {}
        quote_currency_source = None
        if instrument.get("currency"):
            quote_currency_source = "position"
        elif state == "available" and listing.get("currencyCode"):
            quote_currency_source = "instrument_metadata"
        positions.append(
            {
                "ticker": instrument["ticker"],
                "name": instrument.get("name") or listing.get("name"),
                "instrument_currency": instrument.get("currency") or listing.get("currencyCode"),
                "isin": instrument.get("isin") or listing.get("isin"),
                "instrument_type": listing.get("type"),
                "quote_currency_source": quote_currency_source,
                "metadata": {
                    "state": state,
                    "source_id": metadata["source_id"] if metadata else None,
                    "retrieved_at": metadata_payload.get("retrieved_at"),
                },
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
    current_tickers = {row["ticker"] for row in positions if number(row["quantity"]) != 0}
    previous_tickers = {
        row["ticker"]
        for row in (previous or {}).get("positions", [])
        if number(row["quantity"]) != 0
    }
    return {
        "holding_changes": {
            "basis": "previous_saved_snapshot" if previous is not None else "initial_observation",
            "added_tickers": sorted(current_tickers - previous_tickers) if previous else [],
            "closed_tickers": sorted(previous_tickers - current_tickers) if previous else [],
        },
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


async def prepare_exposures(projection, snapshot_id, calculate):
    """Pass only the approved position/control inputs to the private Rust service."""
    if calculate is None:
        return None
    request = {
        "snapshot_id": snapshot_id,
        "account_as_of": projection["account_retrieval"]["retrieval_completed_at"],
        "positions_as_of": projection["positions_retrieval"]["retrieval_completed_at"],
        "currency": projection["currency"],
        "portfolio_value": projection["total_value"],
        "invested_value": projection["investments"]["currentValue"],
        "cash_components": projection["cash_components"],
        "positions": [
            {
                "ticker": row["ticker"],
                "current_value": row["current_value"],
                "account_currency": row["account_currency"],
                "quote_currency": (
                    row["instrument_currency"] if row["quote_currency_source"] else None
                ),
            }
            for row in projection["positions"]
        ],
    }
    try:
        async with asyncio.timeout(5):
            result = json.loads(await calculate(canonical(request)))
        if result.get("method") == "broker_exposures_v1" and all(
            result.get(key) == request[key]
            for key in ("snapshot_id", "account_as_of", "positions_as_of", "currency")
        ):
            return result
    except Exception:
        # The Python Worker bridge raises host-specific errors for failed RPCs.
        pass
    return {"method": "broker_exposures_v1", "availability": "failed"}
