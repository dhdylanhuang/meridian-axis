"""Trusted read-only diagnostic over accepted evidence; no browser grants or writes."""

import hashlib
import json

from sqlalchemy import select

from meridian.adapters.broker_evidence import canonical, identifier, instant, number
from meridian.domain.quantity_history import QuantityRecord, reconcile_quantities
from meridian.persistence.models import (
    Account,
    BrokerEventRevision,
    BrokerSnapshot,
    ImportRun,
    SourceRecord,
)

MAX_OBSERVATIONS = 20_000


class ReconciliationError(ValueError):
    """Safe failure code; never interpolate private source content."""


def _bounded(db, query):
    rows = db.scalars(query.limit(MAX_OBSERVATIONS + 1)).all()
    if len(rows) > MAX_OBSERVATIONS:
        raise ReconciliationError("reconciliation_observation_limit")
    return rows


def _record(raw, *, source_id, observed_at, revision_id=None, revision=0):
    order, fill = raw["order"], raw.get("fill")
    fill_id = identifier(fill["id"]) if fill is not None else None
    order_id = identifier(order["id"])
    return QuantityRecord(
        identity="fill:" + fill_id if fill_id is not None else "order:" + order_id,
        source_id=source_id,
        revision_id=revision_id,
        revision=revision,
        observed_at=observed_at,
        digest=hashlib.sha256(canonical(raw).encode()).hexdigest(),
        order_id=order_id,
        fill_id=fill_id,
        ticker=identifier(order["instrument"]["ticker"]),
        side=order["side"],
        fill_type=fill["type"] if fill is not None else None,
        quantity=number(fill["quantity"]) if fill is not None else None,
        executed_at=instant(fill["filledAt"]) if fill is not None else None,
        executed_at_text=fill["filledAt"] if fill is not None else None,
        price=number(fill["price"]) if fill is not None and fill.get("price") is not None else None,
        price_currency=order.get("currency"),
    )


def history_reconciliation(db, *, account_id):
    """Run within one caller-owned consistent read transaction, on trusted storage.

    Initial captures and ongoing revisions share fill identity. Latest observation
    wins, never sum revision versions. Missing records in later traversals are not
    deletions. Rebuild from immutable evidence with a versioned method, no ledger
    persistence/backfill. Scope is fixed to the selected account and environment.
    """
    account = db.get(Account, account_id)
    if account is None or account.broker != "trading212":
        raise ReconciliationError("reconciliation_account_invalid")
    snapshot = db.scalar(
        select(BrokerSnapshot)
        .where(BrokerSnapshot.account_id == account_id)
        .order_by(BrokerSnapshot.observed_at.desc(), BrokerSnapshot.id.desc())
        .limit(1)
    )
    if snapshot is None:
        raise ReconciliationError("reconciliation_snapshot_unavailable")
    if hashlib.sha256(snapshot.snapshot_json.encode()).hexdigest() != snapshot.digest:
        raise ReconciliationError("reconciliation_snapshot_integrity_invalid")
    projection = json.loads(snapshot.snapshot_json)
    if (
        projection["environment"] != account.environment
        or projection.get("source") != "trading212"
        or projection.get("basis") != "broker_reported"
    ):
        raise ReconciliationError("reconciliation_snapshot_scope_invalid")
    cutoff = instant(projection["positions_retrieval"]["retrieval_completed_at"])
    positions = {}
    for row in projection["positions"]:
        if row["ticker"] in positions:
            raise ReconciliationError("reconciliation_duplicate_position")
        positions[row["ticker"]] = number(row["quantity"])
    captures = _bounded(
        db,
        select(SourceRecord)
        .join(ImportRun, SourceRecord.run_id == ImportRun.id)
        .where(
            SourceRecord.account_id == account_id,
            SourceRecord.kind == "trading212_orders",
            SourceRecord.schema_version == "trading212_capture_v1",
            ImportRun.status == "succeeded",
        ),
    )
    revisions = _bounded(
        db,
        select(BrokerEventRevision)
        .join(SourceRecord, BrokerEventRevision.source_id == SourceRecord.id)
        .join(ImportRun, SourceRecord.run_id == ImportRun.id)
        .where(
            BrokerEventRevision.account_id == account_id,
            BrokerEventRevision.family == "orders",
            ImportRun.status == "succeeded",
        ),
    )
    records = []
    for source in captures:
        if hashlib.sha256(source.payload_json.encode()).hexdigest() != source.digest:
            raise ReconciliationError("reconciliation_source_integrity_invalid")
        payload = json.loads(source.payload_json)
        records.append(
            _record(
                payload["raw"],
                source_id=source.id,
                observed_at=instant(payload["context"]["retrieval_completed_at"]),
            )
        )
    for revision in revisions:
        record = _record(
            json.loads(revision.payload_json),
            source_id=revision.source_id,
            observed_at=revision.observed_at,
            revision_id=revision.id,
            revision=revision.revision,
        )
        if record.identity != revision.external_id or record.digest != revision.digest:
            raise ReconciliationError("reconciliation_revision_integrity_invalid")
        records.append(record)
    latest_attempt = db.scalar(
        select(ImportRun)
        .where(ImportRun.account_id == account_id, ImportRun.kind == "trading212_history_orders")
        .order_by(ImportRun.started_at.desc(), ImportRun.id.desc())
        .limit(1)
    )
    latest_completed = db.scalar(
        select(ImportRun)
        .where(
            ImportRun.account_id == account_id,
            ImportRun.kind == "trading212_history_orders",
            ImportRun.status == "succeeded",
        )
        .order_by(ImportRun.finished_at.desc(), ImportRun.id.desc())
        .limit(1)
    )
    result = reconcile_quantities(records, positions, cutoff=cutoff)
    result.update(
        method="known_trade_quantity_v1",
        availability="provisional",
        source="trading212",
        environment=account.environment,
        snapshot_id=snapshot.id,
        positions_retrieval=projection["positions_retrieval"],
        as_of=cutoff.isoformat(),
        latest_history_observed_at=max((r.observed_at for r in records), default=None),
        coverage={
            "lifetime": "unverified",
            "opening_positions": "not_supplied",
            "observation_count": len(records),
            "initial_capture_rows": len(captures),
            "revision_rows": len(revisions),
            "latest_order_sync_status": latest_attempt.status if latest_attempt else "not_observed",
            "latest_completed_order_sync": (
                latest_completed.finished_at.isoformat() if latest_completed else None
            ),
        },
        cash={"availability": "unsupported", "reason": "cash_signs_fees_fx_and_opening_unverified"},
        dividends={"availability": "unsupported", "reason": "payment_economics_not_normalized"},
        fees={"availability": "unsupported", "reason": "charge_economics_unverified"},
    )
    if result["latest_history_observed_at"] is not None:
        result["latest_history_observed_at"] = result["latest_history_observed_at"].isoformat()
    result["warnings"] += [
        "lifetime_coverage_unverified",
        "opening_positions_not_supplied",
        "separate_history_and_positions_observations",
        "cash_dividends_fees_not_reconciled",
    ]
    return result
