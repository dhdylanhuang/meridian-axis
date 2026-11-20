"""Private job authority wiring. Each invocation owns its connections and secrets."""

import json
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from meridian.adapters.trading212 import Trading212Client
from meridian.application.broker_jobs import BrokerJobs
from meridian.application.broker_metadata import latest_metadata, refresh_metadata
from meridian.application.broker_sessions import relevant_session
from meridian.application.broker_sync import BrokerSync
from meridian.persistence.models import Account, BrokerSnapshot, BrokerSyncJob
from meridian.security.hosted import create_binding_engine


def session_state(engine, account_id, now):
    with Session(engine) as db:
        snapshot = db.scalar(
            select(BrokerSnapshot)
            .where(BrokerSnapshot.account_id == account_id)
            .order_by(BrokerSnapshot.observed_at.desc())
            .limit(1)
        )
        metadata = latest_metadata(db, account_id)
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


async def run_sync(
    binding,
    *,
    api_key,
    api_secret,
    environment,
    scheduled=False,
    reconcile_cash=None,
    calculate_exposures=None,
):
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
            service = BrokerSync(
                engine,
                "shared-isa",
                environment,
                reference,
                api,
                jobs=jobs,
                cash_reconciler=reconcile_cash,
                exposure_calculator=calculate_exposures,
            )
            state = session_state(engine, "shared-isa", jobs.clock()) if scheduled else "manual"
            result = await service.refresh() if state != "closed" else {"status": "outside_session"}
            if scheduled:
                if state == "closed":
                    summary = await api.account_summary()
                    if (summary.account_id, summary.currency) != (reference, "GBP"):
                        raise ValueError("broker_account_scope_invalid")
                elif result.get("status") != "succeeded":
                    return result | {"session": state}
                # One history page per ten-minute slot, rotating families.
                family = ("orders", "dividends", "transactions")[
                    int(jobs.clock().timestamp() // 600) % 3
                ]
                await service.history_page(family)
            if result.get("status") == "succeeded" or (scheduled and state == "closed"):
                await refresh_metadata(service)
            if not scheduled and result["status"] in {"failed", "deferred"}:
                with Session(engine) as db:
                    job = db.get(BrokerSyncJob, ("shared-isa", "snapshot"))
                    if job and job.error_code not in {None, "action_required"} and job.failures < 4:
                        due = max(job.next_attempt_at, jobs.clock() + timedelta(seconds=1))
                        if job.lease_until is not None:
                            due = max(due, job.lease_until)
                        result["retry_at"] = due.isoformat()
            return result | {"session": state}
    finally:
        engine.dispose()


def run_retention(binding):
    """One fixed server-side batch; never load expired payloads into Worker memory."""
    engine = create_binding_engine(binding, expected_role="meridian_sync_public")
    try:
        with engine.begin() as db:
            db.execute(text("SET LOCAL statement_timeout = '5s'"))
            return db.scalar(text("SELECT public.prune_broker_refresh()"))
    finally:
        engine.dispose()
