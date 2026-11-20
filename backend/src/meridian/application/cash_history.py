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
):
    """Read one consistent caller-owned snapshot; never grant runtime raw access.

    Initial capture and accepted revision payloads remain evidence. Every exported
    sign basis is unverified: provider amounts cannot become economic cash deltas
    until separately supported semantics are implemented. Broker components remain
    independent observations, never an invented closing total or opening balance.
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
    revisions = _bounded(
        db,
        select(BrokerEventRevision)
        .join(SourceRecord, BrokerEventRevision.source_id == SourceRecord.id)
        .join(ImportRun, SourceRecord.run_id == ImportRun.id)
        .where(
            BrokerEventRevision.account_id == account_id,
            BrokerEventRevision.family == "transactions",
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

    def append(raw, source_id, observed_at, revision_id=None, revision=0, digest=None):
        encoded_digest = hashlib.sha256(canonical(raw).encode()).hexdigest()
        if digest is not None and digest != encoded_digest:
            raise ReconciliationError("reconciliation_revision_integrity_invalid")
        instant(raw["dateTime"])
        number(raw["amount"])
        observations.append(
            dict(
                scope=scope,
                reference=identifier(raw["reference"]),
                provider_type=identifier(raw["type"]),
                currency=identifier(raw["currency"]),
                amount=str(raw["amount"]),
                occurred_at=raw["dateTime"],
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
        )
    cash = projection["cash_components"]
    return dict(
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
