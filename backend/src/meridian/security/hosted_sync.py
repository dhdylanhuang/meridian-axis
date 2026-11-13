"""Private job authority wiring. Each invocation owns its connections and secrets."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian.adapters.trading212 import Trading212Client
from meridian.application.broker_jobs import BrokerJobs
from meridian.application.broker_sessions import relevant_session
from meridian.application.broker_sync import BrokerSync, decimal_strings, source_record
from meridian.persistence.models import Account, BrokerSnapshot, SourceRecord
from meridian.security.hosted import create_binding_engine


def session_state(engine, account_id, now):
    with Session(engine) as db:
        snapshot = db.scalar(
            select(BrokerSnapshot)
            .where(BrokerSnapshot.account_id == account_id)
            .order_by(BrokerSnapshot.observed_at.desc())
            .limit(1)
        )
        # Metadata sources are immutable and only inserted with successful jobs.
        from meridian.persistence.models import ImportRun

        metadata = db.scalar(
            select(SourceRecord)
            .join(ImportRun, SourceRecord.run_id == ImportRun.id)
            .where(
                SourceRecord.account_id == account_id,
                SourceRecord.kind == "trading212_metadata",
                ImportRun.status == "succeeded",
            )
            .order_by(ImportRun.finished_at.desc())
            .limit(1)
        )
        if snapshot is None or metadata is None:
            return "unknown"
        payload = json.loads(metadata.payload_json)
        if (now - metadata_time(payload)).total_seconds() > 36 * 3600:
            return "unknown"
        return relevant_session(
            now,
            [r["ticker"] for r in json.loads(snapshot.snapshot_json)["positions"]],
            payload["instruments"],
            payload["exchanges"],
        )


def metadata_time(payload):
    from meridian.adapters.broker_evidence import instant

    return instant(payload["retrieved_at"])


async def refresh_metadata(service):
    jobs = service.jobs
    token = jobs.acquire("metadata")
    if token is None:
        return
    try:
        instruments = await service.api.instruments()
        exchanges = await service.api.exchanges()
        payload = dict(
            retrieved_at=jobs.clock().isoformat(),
            instruments=[decimal_strings(r.raw_payload) for r in instruments],
            exchanges=[decimal_strings(r.raw_payload) for r in exchanges],
        )
        with Session(service.engine) as db, db.begin():
            job = jobs.owned(db, "metadata", token)
            service.scope(db)
            run = service.new_run(db, "trading212_metadata")
            db.add(source_record(service.account_id, run.id, 1, "trading212_metadata", payload))
            run.status, run.finished_at = "succeeded", jobs.clock()
            service.audit(db, run, "broker_metadata_accepted", {"families": 2})
            jobs.succeed(job, interval=86400)
    except Exception as error:
        from meridian.adapters.trading212 import BrokerError

        jobs.fail(
            "metadata",
            token,
            error if isinstance(error, BrokerError) else BrokerError("metadata_failed"),
        )


async def run_sync(binding, *, api_key, api_secret, environment, scheduled=False):
    engine = create_binding_engine(binding, expected_role="meridian_sync_public")
    try:
        with Session(engine) as db:
            account = db.get(Account, "shared-isa")
            if (
                account is None
                or account.environment != environment
                or not account.private_reference
            ):
                raise ValueError("broker_account_scope_invalid")
            reference = account.private_reference
        jobs = BrokerJobs(engine, "shared-isa")
        async with Trading212Client(
            api_key=api_key,
            api_secret=api_secret,
            environment=environment,
            max_attempts=1,
            reserve_request=jobs.reserve,
            observe_response=jobs.observe,
        ) as api:
            service = BrokerSync(engine, "shared-isa", environment, reference, api, jobs=jobs)
            state = session_state(engine, "shared-isa", jobs.clock()) if scheduled else "manual"
            result = await service.refresh() if state != "closed" else {"status": "outside_session"}
            if scheduled:
                if state == "closed":
                    summary = await api.account_summary()
                    if (summary.account_id, summary.currency) != (reference, "GBP"):
                        raise ValueError("broker_account_scope_invalid")
                elif result.get("status") != "succeeded":
                    return result | {"session": state}
                # One history page per invocation, rotating families each minute.
                family = ("orders", "dividends", "transactions")[
                    int(jobs.clock().timestamp() // 60) % 3
                ]
                await service.history_page(family)
                await refresh_metadata(service)
            return result | {"session": state}
    finally:
        engine.dispose()
