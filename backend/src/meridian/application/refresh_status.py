"""Browser-safe job health uses column grants and exposes no private checkpoints."""

from sqlalchemy import select

from meridian.persistence.models import BrokerSyncJob


def refresh_status(db, account_id, now):
    job = BrokerSyncJob
    rows = db.execute(
        select(
            job.task,
            job.last_attempt_at,
            job.last_success_at,
            job.next_attempt_at,
            job.failures,
            job.error_code,
        ).where(job.account_id == account_id)
    )
    result = {}
    for task, attempt, success, retry, failures, error in rows:
        result[task] = dict(
            last_attempt_at=attempt.isoformat() if attempt else None,
            last_success_at=success.isoformat() if success else None,
            next_attempt_at=retry.isoformat(),
            failures=failures,
            error=error,
            stale=success is None
            or (now - success).total_seconds() > (120 if task == "snapshot" else 7200),
        )
    return dict(target_interval_seconds=60, quote_age="unknown", jobs=result)
