"""Pure, provisional quantity replay; never a cash, cost or return calculation."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext


@dataclass(frozen=True)
class QuantityRecord:
    identity: str
    source_id: str
    revision_id: str | None
    revision: int
    observed_at: datetime
    digest: str
    order_id: str
    fill_id: str | None
    ticker: str
    side: str
    fill_type: str | None
    quantity: Decimal | None
    executed_at: datetime | None
    executed_at_text: str | None
    price: Decimal | None
    price_currency: str | None


def decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def reconcile_quantities(records, positions, *, cutoff: datetime):
    """Compare known signed TRADE deltas with a separately observed position set.

    No implicit opening quantity is created. Residual = broker minus known deltas,
    not proof of a missing trade. BUY-negative / SELL-positive observations need
    sign review rather than an undocumented abs()/side correction. All other fill
    types remain review records without inferred corporate-action economics.
    """
    grouped = {}
    for record in records:
        grouped.setdefault(record.identity, []).append(record)
    normalized, totals, warnings = [], {}, set()
    with localcontext() as context:
        # Evidence decimals have <=128 digits/exponent; leave headroom for sums.
        context.prec = 600
        for identity, observations in sorted(grouped.items()):
            rank = max((r.observed_at, r.revision) for r in observations)
            candidates = [r for r in observations if (r.observed_at, r.revision) == rank]
            current = min(candidates, key=lambda r: r.source_id)
            conflict = len({r.digest for r in candidates}) != 1
            state, delta = "no_execution", None
            if conflict:
                state = "identity_conflict_review"
            elif current.fill_id is not None:
                if current.fill_type != "TRADE":
                    state = "corporate_action_review"
                elif current.executed_at > cutoff:
                    state = "after_snapshot"
                elif current.side not in ("BUY", "SELL") or (
                    current.quantity < 0 if current.side == "BUY" else current.quantity > 0
                ):
                    state = "quantity_sign_review"
                else:
                    state, delta = "known_trade_delta", current.quantity
                    totals[current.ticker] = totals.get(current.ticker, Decimal(0)) + delta
            if state.endswith("review"):
                warnings.add(state)
            normalized.append(
                {
                    "identity": identity,
                    "order_id": current.order_id,
                    "fill_id": current.fill_id,
                    "ticker": current.ticker,
                    "side": current.side,
                    "fill_type": current.fill_type,
                    "source_quantity": (
                        decimal_text(current.quantity) if current.quantity is not None else None
                    ),
                    "quantity_delta": decimal_text(delta) if delta is not None else None,
                    "executed_at": current.executed_at_text,
                    "price": decimal_text(current.price) if current.price is not None else None,
                    "price_currency": current.price_currency,
                    "state": state,
                    "selected_source_id": current.source_id,
                    "selected_revision_id": current.revision_id,
                    "evidence": [
                        {
                            "source_id": r.source_id,
                            "revision_id": r.revision_id,
                            "revision": r.revision,
                            "digest": r.digest,
                            "observed_at": r.observed_at.isoformat(),
                        }
                        for r in sorted(
                            observations, key=lambda r: (r.observed_at, r.revision, r.source_id)
                        )
                    ],
                }
            )
        comparisons = []
        for ticker in sorted(set(totals) | set(positions) | {r.ticker for r in records}):
            known, broker = totals.get(ticker, Decimal(0)), positions.get(ticker, Decimal(0))
            residual = broker - known
            comparisons.append(
                {
                    "ticker": ticker,
                    "unit": "instrument_units",
                    "known_trade_quantity": decimal_text(known),
                    "broker_quantity": decimal_text(broker),
                    "unexplained_difference": decimal_text(residual),
                    "state": "difference" if residual else "matches_known_events_only",
                }
            )
    return {"records": normalized, "quantities": comparisons, "warnings": sorted(warnings)}
