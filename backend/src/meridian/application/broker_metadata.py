"""One held-listing metadata path, shared by session checks and publication."""

import asyncio
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian.adapters.broker_evidence import canonical, number
from meridian.adapters.trading212 import BrokerError
from meridian.application.broker_sessions import select_session_metadata
from meridian.persistence.models import BrokerSnapshot, ImportRun, SourceRecord


def latest_metadata(db, account_id):
    return db.scalar(
        select(SourceRecord)
        .join(ImportRun, SourceRecord.run_id == ImportRun.id)
        .where(
            SourceRecord.account_id == account_id,
            SourceRecord.kind == "trading212_metadata",
            ImportRun.status == "succeeded",
        )
        .order_by(ImportRun.finished_at.desc(), SourceRecord.id.desc())
        .limit(1)
    )


async def refresh_metadata(service):
    # Serialization is shared with sync; imported here to avoid the publication
    # -> metadata reader -> sync -> publication module dependency cycle.
    from meridian.application.broker_sync import decimal_strings, source_record

    jobs = service.jobs
    with Session(service.engine) as db:
        snapshot = db.scalar(
            select(BrokerSnapshot)
            .where(BrokerSnapshot.account_id == service.account_id)
            .order_by(BrokerSnapshot.observed_at.desc(), BrokerSnapshot.id.desc())
            .limit(1)
        )
        if snapshot is None:
            return
        tickers = sorted(
            row["ticker"]
            for row in json.loads(snapshot.snapshot_json)["positions"]
            if number(row["quantity"]) != 0
        )
    token = jobs.acquire("metadata", metadata_tickers=tickers)
    if token is None:
        return
    try:
        started = jobs.clock().isoformat()
        async with asyncio.timeout(25):
            instruments = await service.api.instruments()
            exchanges = await service.api.exchanges()
        payload = select_session_metadata(
            tickers,
            [decimal_strings(r.raw_payload) for r in instruments],
            [decimal_strings(r.raw_payload) for r in exchanges],
        ) | dict(retrieval_started_at=started, retrieved_at=jobs.clock().isoformat())
        with Session(service.engine) as db, db.begin():
            job = jobs.owned(db, "metadata", token)
            service.scope(db)
            run = service.new_run(db, "trading212_metadata")
            db.add(source_record(service.account_id, run.id, 1, "trading212_metadata", payload))
            run.status, run.finished_at = "succeeded", jobs.clock()
            service.audit(db, run, "broker_metadata_accepted", {"families": 2})
            jobs.succeed(job, interval=86400, checkpoint=canonical({"requested_tickers": tickers}))
    except Exception as error:
        jobs.fail(
            "metadata",
            token,
            error if isinstance(error, BrokerError) else BrokerError("metadata_failed"),
        )
