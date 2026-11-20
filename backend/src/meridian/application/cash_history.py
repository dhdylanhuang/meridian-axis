"""Trusted evidence adapter for the pure Rust core; no inferred cash signs."""

import hashlib
import json

from sqlalchemy import select

from meridian.adapters.broker_evidence import canonical, identifier, instant, number
from meridian.application.history_evidence import (
    MAX_OBSERVATIONS,
    ReconciliationError,
    _bounded,
)
from meridian.persistence.models import (
    Account,
    BrokerEventRevision,
    BrokerSnapshot,
    ImportRun,
    SourceRecord,
)


def cash_history_request(
    db,
    *,
    account_id,
    projection=None,
    snapshot_id=None,
    max_observations=MAX_OBSERVATIONS,
    include_captures=True,
    observed_available_cash=False,
    sign_policy=None,
    reported_activity=False,
    pin_to_cutoff=False,
):
    """Read one consistent caller-owned snapshot; never grant runtime raw access.

    Initial capture and accepted revision payloads remain evidence. Every exported
    sign basis is unverified: provider amounts cannot become economic cash deltas
    unless a trusted caller explicitly selects a separately verified Rust policy.
    Broker components remain independent observations, never an invented total.
    """
    account = db.get(Account, account_id)
    if account is None or account.broker != "trading212":
        raise ReconciliationError("reconciliation_account_invalid")
    if projection is None:
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
        snapshot_id = snapshot.id
    elif not isinstance(snapshot_id, str) or not snapshot_id:
        raise ReconciliationError("reconciliation_snapshot_scope_invalid")
    if (
        projection.get("source") != "trading212"
        or projection.get("basis") != "broker_reported"
        or projection.get("environment") != account.environment
    ):
        raise ReconciliationError("reconciliation_snapshot_scope_invalid")
    scope = {"account_id": account_id, "environment": account.environment}
    cutoff = projection["account_retrieval"]["retrieval_completed_at"]
    instant(cutoff)
    captures = (
        _bounded(
            db,
            select(SourceRecord)
            .join(ImportRun, SourceRecord.run_id == ImportRun.id)
            .where(
                SourceRecord.account_id == account_id,
                SourceRecord.kind == "trading212_transactions",
                SourceRecord.schema_version == "trading212_capture_v1",
                ImportRun.status == "succeeded",
            )
            .order_by(SourceRecord.id),
            limit=max_observations,
        )
        if include_captures
        else []
    )
    families = ["transactions", "dividends"] if reported_activity else ["transactions"]
    revisions = _bounded(
        db,
        select(BrokerEventRevision)
        .join(SourceRecord, BrokerEventRevision.source_id == SourceRecord.id)
        .join(ImportRun, SourceRecord.run_id == ImportRun.id)
        .where(
            BrokerEventRevision.account_id == account_id,
            BrokerEventRevision.family.in_(families),
            (BrokerEventRevision.observed_at <= instant(cutoff)) if pin_to_cutoff else True,
            ImportRun.status == "succeeded",
        )
        .order_by(
            BrokerEventRevision.observed_at, BrokerEventRevision.revision, BrokerEventRevision.id
        ),
        limit=max_observations,
    )
    if len(captures) + len(revisions) > max_observations:
        raise ReconciliationError("reconciliation_observation_limit")
    observations = []

    def append(
        raw,
        source_id,
        observed_at,
        revision_id=None,
        revision=0,
        digest=None,
        family="transactions",
    ):
        encoded_digest = hashlib.sha256(canonical(raw).encode()).hexdigest()
        if digest is not None and digest != encoded_digest:
            raise ReconciliationError("reconciliation_revision_integrity_invalid")
        occurred_at = raw["paidOn"] if family == "dividends" else raw["dateTime"]
        instant(occurred_at)
        number(raw["amount"])
        instrument = raw.get("instrument") or {}
        label = instrument.get("name") or instrument.get("ticker") or raw.get("ticker")
        if label is not None and (
            not isinstance(label, str)
            or not 0 < len(label.encode()) <= 512
            or any(ord(c) < 32 for c in label)
        ):
            raise ReconciliationError("reconciliation_instrument_invalid")
        observations.append(
            dict(
                scope=scope,
                reference=identifier(raw["reference"]),
                provider_type=identifier(
                    raw.get("type", "UNSPECIFIED") if family == "dividends" else raw["type"]
                ),
                currency=identifier(raw["currency"]),
                amount=str(raw["amount"]),
                occurred_at=occurred_at,
                **({"family": family} if reported_activity else {}),
                **({"instrument_label": label} if reported_activity and label else {}),
                observed_at=observed_at,
                source_id=source_id,
                revision_id=revision_id,
                revision=revision,
                digest=encoded_digest,
                sign_basis={"state": "unverified"},
            )
        )

    for source in captures:
        if hashlib.sha256(source.payload_json.encode()).hexdigest() != source.digest:
            raise ReconciliationError("reconciliation_source_integrity_invalid")
        payload = json.loads(source.payload_json)
        if payload["environment"] != account.environment or payload["family"] != "transactions":
            raise ReconciliationError("reconciliation_source_scope_invalid")
        stamp = payload["context"]["retrieval_completed_at"]
        instant(stamp)
        append(payload["raw"], source.id, stamp)
    for revision in revisions:
        raw = json.loads(revision.payload_json)
        if identifier(raw["reference"]) != revision.external_id:
            raise ReconciliationError("reconciliation_revision_integrity_invalid")
        append(
            raw,
            revision.source_id,
            revision.observed_at.isoformat(),
            revision.id,
            revision.revision,
            revision.digest,
            family=revision.family,
        )
    cash = projection["cash_components"]
    request = dict(
        schema_version=1,
        scope=scope,
        cutoff=cutoff,
        observations=observations,
        opening_cash=[],
        closing_cash=[],
        broker_cash=dict(
            currency=projection["currency"],
            available_to_trade=cash.get("availableToTrade"),
            in_pies=cash.get("inPies"),
            reserved_for_orders=cash.get("reservedForOrders"),
            at=cutoff,
            snapshot_id=snapshot_id,
        ),
    )

    if reported_activity:
        request["activity_since"] = (
            instant(cutoff)
            .replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            .isoformat()
        )
    if sign_policy is not None:
        request["cash_sign_policy"] = sign_policy
    if observed_available_cash:
        prior_day = instant(cutoff).replace(hour=0, minute=0, second=0, microsecond=0)
        prior = db.scalar(
            select(BrokerSnapshot)
            .where(BrokerSnapshot.account_id == account_id, BrokerSnapshot.observed_at < prior_day)
            .order_by(BrokerSnapshot.observed_at.desc(), BrokerSnapshot.id.desc())
            .limit(1)
        )
        if prior is not None and cash.get("availableToTrade") is not None:
            if hashlib.sha256(prior.snapshot_json.encode()).hexdigest() != prior.digest:
                raise ReconciliationError("reconciliation_snapshot_integrity_invalid")
            opening = json.loads(prior.snapshot_json)
            amount = opening.get("cash_components", {}).get("availableToTrade")
            if (
                amount is not None
                and opening.get("environment") == account.environment
                and opening.get("currency") == projection["currency"]
            ):
                at = opening["account_retrieval"]["retrieval_completed_at"]
                number(amount)
                if instant(at) >= instant(cutoff):
                    raise ReconciliationError("reconciliation_opening_cutoff_invalid")
                base = dict(
                    scope=scope, currency=projection["currency"], basis="broker_available_to_trade"
                )
                request["opening_cash"] = [base | dict(amount=amount, at=at, source_id=prior.id)]
                request["closing_cash"] = [
                    base | dict(amount=cash["availableToTrade"], at=cutoff, source_id=snapshot_id)
                ]
    return request


def cash_history_coverage(db, *, account_id, cutoff, observations):
    """Completed native traversal metadata, not an assertion of broker lifetime coverage."""
    ids = [
        select(ImportRun.id)
        .where(
            ImportRun.account_id == account_id,
            ImportRun.kind == "trading212_history_" + family,
            ImportRun.status == "succeeded",
            ImportRun.finished_at <= instant(cutoff),
        )
        .order_by(ImportRun.finished_at.desc(), ImportRun.id.desc())
        .limit(1)
        .scalar_subquery()
        for family in ("transactions", "dividends")
    ]
    runs = {
        run.kind.removeprefix("trading212_history_"): run
        for run in db.scalars(
            select(ImportRun).where(ImportRun.account_id == account_id, ImportRun.id.in_(ids))
        )
    }
    result = []
    for family in ("transactions", "dividends"):
        run = runs.get(family)
        pages = json.loads(run.counts_json).get("pages") if run else None
        complete = type(pages) is int and 1 <= pages <= 1000
        dates = [
            instant(row["occurred_at"])
            for row in observations
            if row.get("family", "transactions") == family
            and instant(row["occurred_at"]) <= instant(cutoff)
        ]
        result.append(
            dict(
                family=family,
                state="provider_history_traversed" if complete else "not_established",
                completed_at=run.finished_at.isoformat() if complete else None,
                source_run_id=run.id if complete else None,
                pages=pages if complete else None,
                earliest_observed_at=min(dates).isoformat() if dates else None,
                latest_observed_at=max(dates).isoformat() if dates else None,
            )
        )
    return dict(scope="broker_available_history", lifetime="not_established", families=result)
