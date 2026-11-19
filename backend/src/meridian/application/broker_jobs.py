"""Short durable transactions for shared budgets and fenced, bounded broker work."""

import random
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from meridian.adapters.trading212 import INTERVALS, BrokerError
from meridian.persistence.models import AuditRecord, BrokerRateLimit, BrokerSyncJob, ImportRun


class Deferred(BrokerError):
    def __init__(self, until):
        self.until = until
        super().__init__("request_deferred")


def now_utc():
    return datetime.now(UTC)


class BrokerJobs:
    def __init__(self, engine, account_id, *, clock=now_utc, random_value=random.random):
        self.engine, self.account_id = engine, account_id
        self.clock, self.random = clock, random_value

    def acquire(self, task):
        now, token = self.clock(), uuid4().hex
        with Session(self.engine) as db, db.begin():
            insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
            acquired = db.scalar(
                insert(BrokerSyncJob)
                .values(
                    account_id=self.account_id,
                    task=task,
                    next_attempt_at=now,
                    failures=0,
                    checkpoint_json="{}",
                    lease_token=token,
                    lease_until=now + timedelta(seconds=90),
                    last_attempt_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[BrokerSyncJob.account_id, BrokerSyncJob.task],
                    set_=dict(
                        lease_token=token,
                        lease_until=now + timedelta(seconds=90),
                        last_attempt_at=now,
                    ),
                    where=(BrokerSyncJob.next_attempt_at <= now)
                    & ((BrokerSyncJob.lease_until.is_(None)) | (BrokerSyncJob.lease_until <= now)),
                )
                .returning(BrokerSyncJob.lease_token)
            )
            return acquired

    def resume(self, task, *, actor="administration", restart=False):
        """Trusted maintenance after correcting credentials/schema. Active work is fenced."""
        if task not in {"snapshot", "orders", "dividends", "transactions", "metadata"}:
            raise ValueError("invalid_sync_task")
        import json

        with Session(self.engine) as db, db.begin():
            job = db.scalar(
                select(BrokerSyncJob)
                .where(
                    BrokerSyncJob.account_id == self.account_id,
                    BrokerSyncJob.task == task,
                )
                .with_for_update()
            )
            if job is None:
                return
            if job.lease_until is not None and job.lease_until > self.clock():
                raise ValueError("sync_job_active")
            checkpoint = json.loads(job.checkpoint_json)
            if restart and checkpoint.get("run_id"):
                run = db.get(ImportRun, checkpoint["run_id"])
                if run is not None and run.status == "running":
                    run.status, run.error_code = "failed", "administrative_restart"
                    run.finished_at = self.clock()
            if restart:
                job.checkpoint_json = "{}"
            job.next_attempt_at, job.error_code, job.failures = self.clock(), None, 0
            job.lease_until, job.lease_token = None, None
            db.add(
                AuditRecord(
                    id=uuid4().hex,
                    occurred_at=self.clock(),
                    actor=actor,
                    action="broker_sync_resumed",
                    entity_type="account",
                    entity_id=self.account_id,
                    details_json=json.dumps(dict(task=task, restarted=restart)),
                )
            )

    def owned(self, db, task, token):
        job = db.scalar(
            select(BrokerSyncJob)
            .where(
                BrokerSyncJob.account_id == self.account_id,
                BrokerSyncJob.task == task,
            )
            .with_for_update()
        )
        if job is None or job.lease_token != token or job.lease_until <= self.clock():
            raise BrokerError("lease_lost")
        return job

    def succeed(self, job, *, interval, checkpoint="{}"):
        job.last_success_at = self.clock()
        anchor = job.last_attempt_at
        if job.task == "snapshot":
            # Align to the configured interval so delivery jitter does not skip a slot.
            anchor = datetime.fromtimestamp(int(anchor.timestamp() // interval) * interval, UTC)
        job.next_attempt_at = max(self.clock(), anchor + timedelta(seconds=interval))
        job.failures, job.error_code = 0, None
        job.lease_token, job.lease_until = None, None
        job.checkpoint_json = checkpoint

    def fail(self, task, token, error):
        with Session(self.engine) as db, db.begin():
            try:
                job = self.owned(db, task, token)
            except BrokerError:
                return
            if isinstance(error, Deferred):
                job.next_attempt_at = error.until
                job.error_code = "provider_rate_limited"
            else:
                job.failures += 1
                terminal = error.status in (400, 401, 403, 404) or error.code in {
                    "invalid_response",
                    "invalid_continuation",
                    "account_identity_mismatch",
                    "history_identity_conflict",
                    "pagination_cycle",
                    "pagination_limit",
                }
                # Terminal failures require explicit administrative resume after correction.
                delay = max(
                    600,
                    min(3600, 600 * 2 ** min(job.failures - 1, 3)) * (0.5 + 0.5 * self.random()),
                )
                job.next_attempt_at = (
                    datetime.max.replace(tzinfo=UTC)
                    if terminal
                    else self.clock() + timedelta(seconds=delay)
                )
                job.error_code = "action_required" if terminal else error.code
            job.lease_token, job.lease_until = None, None

    async def reserve(self, route):
        if route not in INTERVALS:
            raise BrokerError("invalid_continuation")
        now = self.clock()
        with Session(self.engine) as db, db.begin():
            insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
            reserved = db.scalar(
                insert(BrokerRateLimit)
                .values(
                    account_id=self.account_id,
                    route=route,
                    next_request_at=now + timedelta(seconds=INTERVALS[route]),
                )
                .on_conflict_do_update(
                    index_elements=[BrokerRateLimit.account_id, BrokerRateLimit.route],
                    set_=dict(next_request_at=now + timedelta(seconds=INTERVALS[route])),
                    where=BrokerRateLimit.next_request_at <= now,
                )
                .returning(BrokerRateLimit.next_request_at)
            )
            if reserved is None:
                until = db.get(BrokerRateLimit, (self.account_id, route)).next_request_at
                raise Deferred(until)

    async def observe(self, route, status, headers):
        now = self.clock()
        deadlines = [now]
        if status == 429 or headers.get("x-ratelimit-remaining") == "0":
            try:
                deadlines.append(
                    datetime.fromtimestamp(float(headers.get("x-ratelimit-reset", "0")), UTC)
                )
            except (ValueError, OverflowError, OSError):
                pass
        retry = headers.get("retry-after")
        if retry is not None and (status == 429 or status >= 500):
            try:
                seconds = float(retry)
                if seconds >= 0:
                    deadlines.append(now + timedelta(seconds=seconds))
            except (ValueError, OverflowError):
                try:
                    stamp = parsedate_to_datetime(retry)
                    if stamp.utcoffset() is not None:
                        deadlines.append(stamp.astimezone(UTC))
                except (ValueError, TypeError, OverflowError):
                    pass
        if status == 429:
            deadlines.append(now + timedelta(seconds=60))
        until = max(deadlines)
        if until <= now:
            return
        with Session(self.engine) as db, db.begin():
            db.execute(
                update(BrokerRateLimit)
                .where(
                    BrokerRateLimit.account_id == self.account_id,
                    BrokerRateLimit.route == route,
                    BrokerRateLimit.next_request_at < until,
                )
                .values(next_request_at=until)
            )
        if status == 429:
            raise Deferred(until)
