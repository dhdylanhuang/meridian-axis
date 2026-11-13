"""Trusted maintenance only; application runtime has no snapshot write grant."""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from meridian.adapters.broker_evidence import canonical, instant
from meridian.application.broker_ingestion import KIND
from meridian.application.broker_snapshot import broker_snapshot
from meridian.application.snapshot_access import MAX_SNAPSHOT_BYTES
from meridian.persistence.models import Account, AuditRecord, BrokerSnapshot, ImportRun


def publish_snapshot(db, *, account_id, run_id, evidence, now=None, actor="administration"):
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
    payload = canonical(broker_snapshot(evidence))
    if len(payload.encode()) > MAX_SNAPSHOT_BYTES:
        raise ValueError("snapshot_size_limit")
    observations = evidence.document["observations"]
    observed = max(
        instant(observations[f]["retrieval_completed_at"]) for f in ("account_summary", "positions")
    )
    snapshot = BrokerSnapshot(
        id=uuid4().hex,
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
