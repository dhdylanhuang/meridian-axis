"""Trusted maintenance only; application runtime has no snapshot write grant."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from meridian.adapters.broker_evidence import canonical, instant
from meridian.application.broker_ingestion import KIND
from meridian.application.broker_metadata import latest_metadata
from meridian.application.broker_snapshot import broker_snapshot
from meridian.application.snapshot_access import MAX_SNAPSHOT_BYTES
from meridian.persistence.models import Account, AuditRecord, BrokerSnapshot, ImportRun


def publish_snapshot(
    db,
    *,
    account_id,
    run_id,
    evidence,
    now=None,
    actor="administration",
    snapshot_id=None,
    reconciliation=None,
):
    now = now or datetime.now(UTC)
    account = db.get(Account, account_id)
    run = db.get(ImportRun, run_id)
    if (
        account is None
        or run is None
        or (run.account_id, run.status, run.content_hash)
        != (account_id, "succeeded", evidence.content_hash)
        or run.kind != (KIND if evidence.document["version"] == 1 else "trading212_refresh")
        or (account.environment, account.private_reference)
        != (evidence.environment, evidence.broker_reference)
    ):
        raise ValueError("snapshot_source_scope_invalid")
    existing = db.scalar(
        select(BrokerSnapshot).where(
            BrokerSnapshot.source_run_id == run_id, BrokerSnapshot.account_id == account_id
        )
    )
    if existing is not None:
        return existing
    observations = evidence.document["observations"]
    observed = max(
        instant(observations[f]["retrieval_completed_at"]) for f in ("account_summary", "positions")
    )
    metadata = latest_metadata(db, account_id)
    previous = db.scalar(
        select(BrokerSnapshot)
        .where(BrokerSnapshot.account_id == account_id, BrokerSnapshot.observed_at <= observed)
        .order_by(BrokerSnapshot.observed_at.desc(), BrokerSnapshot.id.desc())
        .limit(1)
    )
    projection = broker_snapshot(
        evidence,
        metadata={"source_id": metadata.id, "payload": json.loads(metadata.payload_json)}
        if metadata
        else None,
        previous=json.loads(previous.snapshot_json) if previous else None,
    )
    snapshot_id = snapshot_id or uuid4().hex
    if reconciliation is not None:
        if reconciliation.get("source_snapshot_id") != snapshot_id:
            raise ValueError("reconciliation_snapshot_mismatch")
        projection["cash_reconciliation"] = reconciliation
    payload = canonical(projection)
    if len(payload.encode()) > MAX_SNAPSHOT_BYTES:
        raise ValueError("snapshot_size_limit")
    snapshot = BrokerSnapshot(
        id=snapshot_id,
        account_id=account_id,
        source_run_id=run_id,
        observed_at=observed,
        created_at=now,
        snapshot_json=payload,
        digest=hashlib.sha256(payload.encode()).hexdigest(),
    )
    db.add(snapshot)
    db.add(
        AuditRecord(
            id=uuid4().hex,
            occurred_at=now,
            actor=actor,
            action="broker_snapshot_published",
            entity_type="import_run",
            entity_id=run_id,
            run_id=run_id,
            details_json='{"basis":"broker_reported"}',
        )
    )
    db.flush()
    return snapshot
