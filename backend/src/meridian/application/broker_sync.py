"""Read-only bounded sync. Upstream I/O is outside every database transaction."""

import asyncio
import hashlib
import json
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian.adapters.broker_evidence import EvidenceError, canonical, identifier, validate_refresh
from meridian.adapters.trading212 import PREFIX, BrokerError
from meridian.application.broker_jobs import BrokerJobs
from meridian.application.broker_snapshot import broker_snapshot
from meridian.application.snapshot_publish import publish_snapshot
from meridian.persistence.models import (
    Account,
    AuditRecord,
    BrokerEventRevision,
    ImportRun,
    SourceRecord,
)

HISTORY = ("orders", "dividends", "transactions")
MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_PAGES = 1000


def decimal_strings(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: decimal_strings(child) for key, child in value.items()}
    if isinstance(value, list):
        return [decimal_strings(child) for child in value]
    return value


def source_record(account_id, run_id, number, kind, payload):
    encoded = canonical(payload)
    if len(encoded.encode()) > MAX_PAGE_BYTES:
        raise BrokerError("source_size_limit")
    return SourceRecord(
        id=uuid4().hex,
        account_id=account_id,
        run_id=run_id,
        row_number=number,
        kind=kind,
        schema_version="trading212_sync_v2",
        payload_json=encoded,
        digest=hashlib.sha256(encoded.encode()).hexdigest(),
    )


class BrokerSync:
    def __init__(self, engine, account_id, environment, expected_reference, api, *, jobs=None):
        self.engine, self.account_id = engine, account_id
        self.environment, self.reference, self.api = environment, expected_reference, api
        self.jobs = jobs or BrokerJobs(engine, account_id)
        if api.environment != environment:
            raise BrokerError("account_identity_mismatch")
        with Session(engine) as db:
            self.scope(db)

    def scope(self, db):
        account = db.get(Account, self.account_id)
        if account is None or (
            account.environment,
            account.private_reference,
            account.currency,
            account.broker,
            account.wrapper,
        ) != (self.environment, self.reference, "GBP", "trading212", "isa"):
            raise BrokerError("account_identity_mismatch")

    def audit(self, db, run, action, details):
        db.add(
            AuditRecord(
                id=uuid4().hex,
                occurred_at=self.jobs.clock(),
                actor="broker-sync",
                action=action,
                entity_type="import_run",
                entity_id=run.id,
                run_id=run.id,
                details_json=canonical(details),
            )
        )

    def new_run(self, db, kind):
        run = ImportRun(
            id=uuid4().hex,
            account_id=self.account_id,
            kind=kind,
            status="running",
            started_at=self.jobs.clock(),
            counts_json="{}",
        )
        db.add(run)
        db.flush()
        return run

    async def refresh(self):
        task = "snapshot"
        token = self.jobs.acquire(task)
        if token is None:
            return {"status": "deferred"}
        run_id = None
        try:
            with Session(self.engine) as db, db.begin():
                self.jobs.owned(db, task, token)
                self.scope(db)
                # Expired snapshot attempts have no source/publication effects.
                abandoned = db.scalars(
                    select(ImportRun).where(
                        ImportRun.account_id == self.account_id,
                        ImportRun.kind == "trading212_refresh",
                        ImportRun.status == "running",
                    )
                )
                for old in abandoned:
                    old.status, old.error_code = "failed", "lease_expired"
                    old.finished_at = self.jobs.clock()
                run_id = self.new_run(db, "trading212_refresh").id
            observations = {}
            async with asyncio.timeout(65):
                for family, method in (
                    ("account_summary", self.api.account_summary),
                    ("positions", self.api.positions),
                ):
                    start = self.jobs.clock().isoformat()
                    values = await method()
                    rows = [values] if family == "account_summary" else values
                    observations[family] = {
                        "retrieval_started_at": start,
                        "retrieval_completed_at": self.jobs.clock().isoformat(),
                        "traversal_complete": True,
                        "records": [decimal_strings(row.raw_payload) for row in rows],
                    }
            document = dict(
                version=2,
                environment=self.environment,
                source="trading212_api_v0",
                numeric_encoding="decimal_strings",
                observations=observations,
            )
            evidence = validate_refresh(canonical(document).encode())
            if evidence.broker_reference != self.reference:
                raise BrokerError("account_identity_mismatch")
            broker_snapshot(evidence)
            with Session(self.engine) as db, db.begin():
                job = self.jobs.owned(db, task, token)
                self.scope(db)
                run = db.get(ImportRun, run_id)
                db.add(source_record(self.account_id, run_id, 1, "trading212_refresh", document))
                run.status, run.content_hash = "succeeded", evidence.content_hash
                run.finished_at = self.jobs.clock()
                run.counts_json = '{"source_records_added":1,"economic_events_added":0}'
                db.flush()
                publish_snapshot(
                    db,
                    account_id=self.account_id,
                    run_id=run_id,
                    evidence=evidence,
                    now=self.jobs.clock(),
                    actor="broker-sync",
                )
                self.jobs.succeed(job, interval=60)
            return {"status": "succeeded"}
        except Exception as error:
            safe = (
                error
                if isinstance(error, BrokerError)
                else BrokerError(
                    "invalid_response" if isinstance(error, EvidenceError) else "refresh_failed"
                )
            )
            self.jobs.fail(task, token, safe)
            if run_id is not None:
                with Session(self.engine) as db, db.begin():
                    run = db.get(ImportRun, run_id)
                    if run.status == "running":
                        run.status, run.error_code = "failed", safe.code
                        run.finished_at = self.jobs.clock()
            return {"status": "failed", "error": safe.code}

    async def history_page(self, family):
        if family not in HISTORY:
            raise BrokerError("invalid_history_family")
        token = self.jobs.acquire(family)
        if token is None:
            return {"status": "deferred"}
        try:
            with Session(self.engine) as db, db.begin():
                job = self.jobs.owned(db, family, token)
                self.scope(db)
                checkpoint = json.loads(job.checkpoint_json)
                if not checkpoint:
                    run = self.new_run(db, "trading212_history_" + family)
                    checkpoint = dict(
                        run_id=run.id,
                        path=PREFIX + "history/" + family + "?limit=50",
                        seen=[],
                        pages=0,
                    )
                    # Persist the traversal before making its first request.
                    job.checkpoint_json = canonical(checkpoint)
            path, run_id = checkpoint["path"], checkpoint["run_id"]
            if path in checkpoint["seen"]:
                raise BrokerError("pagination_cycle")
            if checkpoint["pages"] >= MAX_PAGES:
                raise BrokerError("pagination_limit")
            started = self.jobs.clock().isoformat()
            async with asyncio.timeout(35):
                rows, continuation = await self.api.history_page(family, path)
            payload = dict(
                family=family,
                retrieval_started_at=started,
                retrieval_completed_at=self.jobs.clock().isoformat(),
                records=[decimal_strings(row.raw_payload) for row in rows],
                next_page_path=continuation,
            )
            if continuation is not None and continuation in [*checkpoint["seen"], path]:
                raise BrokerError("pagination_cycle")
            with Session(self.engine) as db, db.begin():
                job = self.jobs.owned(db, family, token)
                self.scope(db)
                run = db.get(ImportRun, run_id)
                if run.status != "running":
                    raise BrokerError("history_run_invalid")
                source = source_record(
                    self.account_id,
                    run_id,
                    checkpoint["pages"] + 1,
                    "trading212_history_page",
                    payload,
                )
                db.add(source)
                db.flush()
                checkpoint["seen"].append(path)
                checkpoint["pages"] += 1
                checkpoint["path"] = continuation
                if continuation is None:
                    added = self.accept_history(db, run, family)
                    run.status, run.finished_at = "succeeded", self.jobs.clock()
                    run.counts_json = canonical(
                        dict(pages=checkpoint["pages"], revisions_added=added)
                    )
                    self.audit(
                        db,
                        run,
                        "broker_history_accepted",
                        dict(
                            family=family,
                            pages=checkpoint["pages"],
                            revisions_added=added,
                            lifetime_coverage="unverified",
                        ),
                    )
                    self.jobs.succeed(job, interval=3600)
                else:
                    # Page progress is durable. It is never a completed history watermark.
                    job.checkpoint_json = canonical(checkpoint)
                    job.failures, job.error_code = 0, None
                    job.next_attempt_at = self.jobs.clock()
                    job.lease_token, job.lease_until = None, None
            return {"status": "succeeded" if continuation is None else "in_progress"}
        except Exception as error:
            safe = error if isinstance(error, BrokerError) else BrokerError("history_failed")
            self.jobs.fail(family, token, safe)
            return {"status": "failed", "error": safe.code}

    def accept_history(self, db, run, family):
        sources = db.scalars(
            select(SourceRecord)
            .where(SourceRecord.run_id == run.id, SourceRecord.account_id == self.account_id)
            .order_by(SourceRecord.row_number)
        )
        seen, added = {}, 0
        for source in sources:
            for row in json.loads(source.payload_json)["records"]:
                if family == "orders":
                    fill = row.get("fill")
                    external_id = (
                        "fill:" + identifier(fill["id"])
                        if fill is not None
                        else "order:" + identifier(row["order"]["id"])
                    )
                    quality = (
                        "corporate_action_review"
                        if fill and fill["type"] != "TRADE"
                        else "observed"
                    )
                else:
                    external_id, quality = identifier(row["reference"]), "observed"
                encoded = canonical(row)
                digest = hashlib.sha256(encoded.encode()).hexdigest()
                if external_id in seen:
                    if seen[external_id] != digest:
                        raise BrokerError("history_identity_conflict")
                    continue
                seen[external_id] = digest
                previous = db.scalar(
                    select(BrokerEventRevision)
                    .where(
                        BrokerEventRevision.account_id == self.account_id,
                        BrokerEventRevision.family == family,
                        BrokerEventRevision.external_id == external_id,
                    )
                    .order_by(BrokerEventRevision.revision.desc())
                    .limit(1)
                )
                if previous is not None and previous.digest == digest:
                    continue
                db.add(
                    BrokerEventRevision(
                        id=uuid4().hex,
                        account_id=self.account_id,
                        family=family,
                        external_id=external_id,
                        revision=1 if previous is None else previous.revision + 1,
                        source_id=source.id,
                        observed_at=self.jobs.clock(),
                        digest=digest,
                        payload_json=encoded,
                        quality=quality,
                    )
                )
                added += 1
        return added
