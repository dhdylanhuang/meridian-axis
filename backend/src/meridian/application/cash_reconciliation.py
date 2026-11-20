"""Fail-open private Rust call and strict approved snapshot projection."""

import asyncio
import hashlib
import json
import re

from sqlalchemy.orm import Session

from meridian.adapters.broker_evidence import canonical
from meridian.application.cash_history import cash_history_request
from meridian.application.history_evidence import ReconciliationError

METHOD = "cash_reconciliation_rust_v1"
MAX_BYTES = 512 * 1024
MAX_EVENTS = 1024
CASH_TYPES = {
    "DEPOSIT",
    "WITHDRAW",
    "FEE",
    "TRANSFER",
    "INTEREST_ON_FREE_CASH",
    "LENDING_INTEREST",
    "OTHER",
}
REVIEW_STATES = {"unverified_sign_review", "identity_conflict_review", "unsupported_type_review"}
WARNINGS = {
    "lifetime_coverage_unverified",
    "execution_wallets_and_dividends_not_included",
    "no_return_calculation",
    "broker_cash_components_not_a_comparable_total",
    "identity_conflict_review",
    "unsupported_type_review",
    "cash_signs_unverified",
    "transfer_boundary_not_classified",
    "cash_controls_incomplete",
    "available_cash_component_not_total_cash",
}
COVERAGE = {
    "families": ["cash_transactions"],
    "lifetime": "unverified",
    "initial_capture": "not_included_runtime",
    "opening_cash": "not_supplied",
    "signs": "unverified",
}


def unavailable(*, cutoff, snapshot_id, availability="failed", reason="reconciliation_unavailable"):
    return dict(
        method=METHOD,
        availability=availability,
        as_of=cutoff,
        source_snapshot_id=snapshot_id,
        reason=reason,
        input_revision=None,
        event_count=None,
        observation_count=None,
        review_counts={},
        cash=[],
        warnings=["cash_reconciliation_unavailable"],
        coverage=COVERAGE,
    )


def _count(value):
    if type(value) is not int or not 0 <= value <= MAX_EVENTS:
        raise ValueError("reconciliation_result_invalid")
    return value


def approved_summary(raw, request, encoded):
    if not isinstance(raw, str) or len(raw.encode()) > 16 * 1024:
        raise ValueError("reconciliation_result_invalid")
    result = json.loads(raw)
    expected = {
        "method",
        "availability",
        "scope",
        "as_of",
        "source_snapshot_id",
        "input_revision",
        "event_count",
        "observation_count",
        "review_counts",
        "cash",
        "warnings",
    }
    if (
        not isinstance(result, dict)
        or not expected <= set(result) <= expected | {"activity_counts", "cash_sign_policy"}
        or (
            result["method"] != METHOD
            or result["scope"] != request["scope"]
            or result["as_of"] != request["cutoff"]
            or result["source_snapshot_id"] != request["broker_cash"]["snapshot_id"]
            or result["input_revision"] != hashlib.sha256(encoded.encode()).hexdigest()
            or result["availability"] not in {"provisional", "insufficient_data"}
        )
    ):
        raise ValueError("reconciliation_result_mismatch")
    if result.get("cash_sign_policy") != request.get("cash_sign_policy"):
        raise ValueError("reconciliation_result_mismatch")
    events, observations = _count(result["event_count"]), _count(result["observation_count"])
    if events > observations or observations != len(request["observations"]):
        raise ValueError("reconciliation_result_invalid")
    activity = result.get("activity_counts")
    if activity is not None and (
        not isinstance(activity, dict)
        or set(activity) - CASH_TYPES
        or sum(_count(value) for value in activity.values()) != events
    ):
        raise ValueError("reconciliation_result_invalid")
    reviews = result["review_counts"]
    if (
        not isinstance(reviews, dict)
        or set(reviews) - REVIEW_STATES
        or sum(_count(v) for v in reviews.values()) > events
    ):
        raise ValueError("reconciliation_result_invalid")
    if not isinstance(result["warnings"], list) or any(
        w not in WARNINGS for w in result["warnings"]
    ):
        raise ValueError("reconciliation_result_invalid")
    currencies = {row["currency"] for row in request["observations"]} | {
        request["broker_cash"]["currency"]
    }
    cash = result["cash"]
    if not isinstance(cash, list) or len(cash) != len(currencies):
        raise ValueError("reconciliation_result_invalid")
    if {row.get("currency") for row in cash} != currencies:
        raise ValueError("reconciliation_result_invalid")
    base_keys = {"currency", "state", "unexplained_difference"}
    window_keys = {
        "basis",
        "opening_balance",
        "closing_balance",
        "opening_source_snapshot_id",
        "window_start",
        "cutoff",
        "known_signed_movements",
        "replayed_cash",
        "included_movement_count",
        "excluded_movement_count",
    }
    controls = {row["currency"]: row for row in request.get("opening_cash", [])}
    closing = {row["currency"]: row for row in request.get("closing_cash", [])}
    for row in cash:
        control, end = controls.get(row["currency"]), closing.get(row["currency"])
        if control is None or end is None:
            if (
                set(row) != base_keys
                or row["state"] != "insufficient_data"
                or row["unexplained_difference"] is not None
            ):
                raise ValueError("reconciliation_result_invalid")
            continue
        if (
            set(row) != base_keys | window_keys
            or row["basis"] != control["basis"]
            or row["basis"] != "broker_available_to_trade"
            or row["opening_balance"] != control["amount"]
            or row["closing_balance"] != end["amount"]
            or row["opening_source_snapshot_id"] != control["source_id"]
            or row["window_start"] != control["at"]
            or row["cutoff"] != request["cutoff"]
            or row["state"] not in {"difference", "matches_known_events_only"}
            or _count(row["included_movement_count"]) + _count(row["excluded_movement_count"])
            > events
        ):
            raise ValueError("reconciliation_result_invalid")
        for key in ("known_signed_movements", "replayed_cash", "unexplained_difference"):
            value = row[key]
            if (
                not isinstance(value, str)
                or len(value) > 600
                or re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value) is None
            ):
                raise ValueError("reconciliation_result_invalid")
    coverage = dict(COVERAGE)
    if controls:
        coverage["opening_cash"] = "observed_available_to_trade_component"
    if request.get("cash_sign_policy"):
        coverage["signs"] = "statement_checked_gbp_interest_and_transfers_only"
    return {key: result[key] for key in expected - {"scope"}} | {
        "coverage": coverage,
        "activity_counts": activity,
        **(
            {"cash_sign_policy": result["cash_sign_policy"]} if "cash_sign_policy" in result else {}
        ),
    }


async def prepare_cash_summary(engine, *, account_id, projection, snapshot_id, reconcile):
    cutoff = projection["account_retrieval"]["retrieval_completed_at"]
    fallback = dict(cutoff=cutoff, snapshot_id=snapshot_id)
    if reconcile is None:
        return unavailable(**fallback, availability="unsupported", reason="engine_not_configured")
    try:
        # No transaction or checked-out connection spans the service/Rust call.
        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                connection.exec_driver_sql(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                connection.exec_driver_sql("SET LOCAL statement_timeout = '2s'")
            else:
                connection.exec_driver_sql("BEGIN")
            with Session(bind=connection) as db:
                request = cash_history_request(
                    db,
                    account_id=account_id,
                    projection=projection,
                    snapshot_id=snapshot_id,
                    max_observations=MAX_EVENTS,
                    include_captures=False,
                    observed_available_cash=True,
                    sign_policy="statement_checked_gbp_v1",
                )
            connection.rollback()
        encoded = canonical(request)
        if len(encoded.encode()) > MAX_BYTES:
            return unavailable(**fallback, availability="unsupported", reason="history_limit")
        async with asyncio.timeout(4):
            raw = await reconcile(encoded)
        return approved_summary(raw, request, encoded)
    except ReconciliationError as error:
        return unavailable(
            **fallback,
            availability="unsupported"
            if str(error) == "reconciliation_observation_limit"
            else "failed",
            reason="history_limit"
            if str(error) == "reconciliation_observation_limit"
            else "reconciliation_unavailable",
        )
    except Exception:
        return unavailable(**fallback)
