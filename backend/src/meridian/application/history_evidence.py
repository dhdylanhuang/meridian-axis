"""Shared bounded evidence reads and safe errors; no calculation dependency."""

MAX_OBSERVATIONS = 20_000


class ReconciliationError(ValueError):
    """Safe failure code; never interpolate private source content."""


def _bounded(db, query, *, limit=MAX_OBSERVATIONS):
    rows = db.scalars(query.limit(limit + 1)).all()
    if len(rows) > limit:
        raise ReconciliationError("reconciliation_observation_limit")
    return rows
