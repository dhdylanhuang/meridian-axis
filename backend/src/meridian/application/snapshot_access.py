"""Finite read of the approved projection; no raw evidence or broker calls."""

import hashlib
import json
import re
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select, text

from meridian.persistence.models import BrokerSnapshot

MAX_SNAPSHOT_BYTES = 512 * 1024


def read_snapshot(db, account_id):
    row = db.scalar(
        select(BrokerSnapshot)
        .where(BrokerSnapshot.account_id == account_id)
        .order_by(BrokerSnapshot.observed_at.desc(), BrokerSnapshot.id.desc())
        .limit(1)
    )
    if row is None:
        return None
    result = decode_snapshot(row.snapshot_json, row.digest)
    if result.get("source") != "trading212" or result.get("basis") != "broker_reported":
        raise RuntimeError("snapshot_contract_invalid")
    return result


def decode_snapshot(snapshot_json, digest):
    data = snapshot_json.encode()
    if len(data) > MAX_SNAPSHOT_BYTES or hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError("snapshot_integrity_failed")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise RuntimeError("snapshot_contract_invalid")
    return result


HISTORY_DAYS = 90
_AMOUNT = re.compile(r"-?[0-9]+(?:\.[0-9]+)?\Z")

# Transfer only the selected account fields over Hyperdrive. A digest mismatch
# leaves this saved day unavailable rather than substituting an earlier capture.
_POSTGRES_PROJECTION = """
, verified AS MATERIALIZED (
    SELECT day, observed_at,
        CASE WHEN octet_length(snapshot_json) <= :max_bytes
            AND encode(sha256(convert_to(snapshot_json, 'UTF8')), 'hex') = digest
            THEN CAST(snapshot_json AS json) END AS snapshot
    FROM selected
)
SELECT day, observed_at,
    snapshot->>'source' AS source, snapshot->>'basis' AS basis,
    snapshot->>'currency' AS currency,
    CASE WHEN json_typeof(snapshot->'total_value') = 'string'
        THEN snapshot->>'total_value' END AS total_value,
    snapshot->'account_retrieval'->>'retrieval_completed_at' AS account_captured_at
FROM verified ORDER BY day
"""


def _history_fields(row, postgres):
    if postgres:
        return row
    try:
        snapshot = decode_snapshot(row["snapshot_json"], row["digest"])
    except (RuntimeError, ValueError):
        return {}
    retrieval = snapshot.get("account_retrieval")
    return snapshot | {
        "account_captured_at": (
            retrieval.get("retrieval_completed_at") if isinstance(retrieval, dict) else None
        )
    }


def read_history(db, account_id, now):
    """Keep one saved observation per UTC day, with explicit missing days."""
    now = now.astimezone(UTC)
    today = now.date()
    start = today - timedelta(days=HISTORY_DAYS - 1)
    params = {"account_id": account_id, "max_bytes": MAX_SNAPSHOT_BYTES}
    ranges = []
    for index in range(HISTORY_DAYS):
        day = start + timedelta(days=index)
        lower = datetime.combine(day, time.min, UTC)
        upper = min(lower + timedelta(days=1), now + timedelta(microseconds=1))
        params.update(
            {
                f"day{index}": day.isoformat(),
                f"lower{index}": lower.isoformat(timespec="microseconds"),
                f"upper{index}": upper.isoformat(timespec="microseconds"),
            }
        )
        ranges.append(f"(:day{index}, :lower{index}, :upper{index})")
    postgres = db.get_bind().dialect.name == "postgresql"
    projection = _POSTGRES_PROJECTION if postgres else "SELECT * FROM selected ORDER BY day"
    # Bound the reads with the existing account + observation timestamp index.
    statement = text(f"""
        WITH days(day, lower_at, upper_at) AS (VALUES {", ".join(ranges)}),
        selected AS (
            SELECT days.day, saved.observed_at, saved.snapshot_json, saved.digest
            FROM days
            LEFT JOIN broker_snapshots AS saved ON saved.id = (
                SELECT candidate.id FROM broker_snapshots AS candidate
                WHERE candidate.account_id = :account_id
                    AND candidate.observed_at >= days.lower_at
                    AND candidate.observed_at < days.upper_at
                ORDER BY candidate.observed_at DESC, candidate.id DESC LIMIT 1
            ) AND saved.account_id = :account_id
        )
        {projection}
    """)
    points = []
    for row in db.execute(statement, params).mappings():
        point = {"date": row["day"], "status": "missing"}
        if row["observed_at"] is not None:
            point["status"] = "unavailable"
            fields = _history_fields(row, postgres)
            amount = fields.get("total_value")
            captured = fields.get("account_captured_at")
            if (
                fields.get("source") == "trading212"
                and fields.get("basis") == "broker_reported"
                and fields.get("currency") == "GBP"
                and isinstance(amount, str)
                and _AMOUNT.fullmatch(amount)
                and isinstance(captured, str)
            ):
                try:
                    observed_at = datetime.fromisoformat(row["observed_at"])
                    captured_at = datetime.fromisoformat(captured)
                    if captured_at.utcoffset() is not None and captured_at <= observed_at:
                        point.update(
                            status="observed",
                            total_value=amount,
                            captured_at=captured_at.astimezone(UTC).isoformat(),
                            observed_at=observed_at.isoformat(),
                        )
                except ValueError:
                    pass
        points.append(point)
    return {
        "source": "trading212",
        "basis": "broker_reported",
        "currency": "GBP",
        "as_of": now.isoformat(),
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "days": points,
    }
