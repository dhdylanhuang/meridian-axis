"""Finite read of the approved projection; no raw evidence or broker calls."""

import hashlib
import json
import re
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

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
_VUAG_TICKER = "VUAGl_EQ"
_VUAG_ISIN = "IE00BFMXXD54"
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
    {benchmark_projection}
FROM verified ORDER BY day
"""

_VUAG_PROJECTION = """
, snapshot->'positions_retrieval'->>'retrieval_completed_at' AS positions_captured_at
, (SELECT CAST(json_agg(json_build_object(
        'isin', pos->>'isin',
        'instrument_currency', pos->>'instrument_currency',
        'current_price', CASE WHEN json_typeof(pos->'current_price') = 'string'
            THEN pos->>'current_price' END
    )) AS text)
    FROM (
        SELECT pos FROM json_array_elements(
            CASE WHEN json_typeof(snapshot->'positions') = 'array'
                THEN snapshot->'positions' ELSE '[]' END
        ) AS position(pos)
        WHERE pos->>'ticker' = :vuag_ticker
        LIMIT 2
    ) AS selected_positions
) AS vuag_positions_json
"""


def _vuag_mark(fields, postgres, observed_at):
    if postgres:
        positions = json.loads(fields.get("vuag_positions_json") or "[]")
        captured = fields.get("positions_captured_at")
    else:
        saved = fields.get("positions")
        positions = (
            [row for row in saved if isinstance(row, dict) and row.get("ticker") == _VUAG_TICKER]
            if isinstance(saved, list)
            else []
        )
        retrieval = fields.get("positions_retrieval")
        captured = retrieval.get("retrieval_completed_at") if isinstance(retrieval, dict) else None
    if len(positions) != 1 or not isinstance(captured, str):
        return None
    row = positions[0]
    price = row.get("current_price")
    if (
        row.get("isin") not in (None, _VUAG_ISIN)
        or row.get("instrument_currency") != "GBP"
        or not isinstance(price, str)
        or len(price) > 128
        or not _AMOUNT.fullmatch(price)
        or Decimal(price) <= 0
    ):
        return None
    try:
        at = datetime.fromisoformat(captured)
    except ValueError:
        return None
    if at.utcoffset() is None or at > observed_at:
        return None
    return {"price_gbp": price, "at": at.astimezone(UTC).isoformat()}


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


def _daily_snapshots(db, account_id, now, days, projection, extra_params=None):
    params = {"account_id": account_id}
    params.update(extra_params or {})
    ranges = []
    for index, day in enumerate(days):
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
    # Bound the reads with the existing account + observation timestamp index.
    statement = text(f"""
        WITH days(day, lower_at, upper_at) AS (VALUES {", ".join(ranges)}),
        selected AS (
            SELECT days.day, saved.id, saved.observed_at, saved.snapshot_json, saved.digest
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
    return db.execute(statement, params).mappings()


def _capture(value, observed_at):
    if isinstance(value, str):
        try:
            captured = datetime.fromisoformat(value)
            if captured.utcoffset() is not None and captured <= observed_at:
                return captured.astimezone(UTC).isoformat()
        except ValueError:
            pass
    return None


def read_changes_endpoints(db, account_id, now, start, end):
    """Return two bounded, digest-checked inputs to the gateway's Rust calculator."""
    endpoints = []
    for row in _daily_snapshots(
        db, account_id, now, (start, end), "SELECT * FROM selected ORDER BY day"
    ):
        endpoint = {"date": row["day"], "status": "missing"}
        endpoints.append(endpoint)
        if row["id"] is None:
            continue
        observed = datetime.fromisoformat(row["observed_at"]).astimezone(UTC)
        endpoint.update(status="unavailable", observed_at=observed.isoformat())
        fields = _history_fields(row, False)
        if (
            fields.get("source") != "trading212"
            or fields.get("basis") != "broker_reported"
            or fields.get("currency") != "GBP"
        ):
            continue
        captures = {}
        for name in ("account", "positions"):
            retrieval = fields.get(f"{name}_retrieval")
            captures[f"{name}_captured_at"] = _capture(
                retrieval.get("retrieval_completed_at") if isinstance(retrieval, dict) else None,
                observed,
            )
        positions = fields.get("positions")
        if not all(captures.values()) or not isinstance(positions, list) or len(positions) > 1024:
            continue
        tickers = set()
        selected = []
        for position in positions:
            ticker = position.get("ticker") if isinstance(position, dict) else None
            if not isinstance(ticker, str) or not ticker or ticker in tickers:
                break
            tickers.add(ticker)
            selected.append(
                {
                    key: position.get(key) if isinstance(position.get(key), str) else None
                    for key in (
                        "ticker",
                        "name",
                        "isin",
                        "quantity",
                        "current_value",
                        "account_currency",
                    )
                }
            )
        else:
            exposure = fields.get("exposures")
            if not isinstance(exposure, dict) or (
                exposure.get("method") != "broker_exposures_v1"
                or exposure.get("snapshot_id") != row["id"]
                or exposure.get("currency") != "GBP"
                or _capture(exposure.get("account_as_of"), observed)
                != captures["account_captured_at"]
                or _capture(exposure.get("positions_as_of"), observed)
                != captures["positions_captured_at"]
            ):
                exposure = {}
            endpoint.update(
                captures,
                status="observed",
                snapshot_id=row["id"],
                portfolio_value=fields.get("total_value"),
                invested_value=(fields.get("investments") or {}).get("currentValue"),
                cash=fields.get("cash_components") or {},
                positions=selected,
                allocations={
                    key: exposure[key]
                    for key in ("sectors", "issuer_domiciles", "fund_markets")
                    if key in exposure
                },
            )
    return {"start": endpoints[0], "end": endpoints[1]}


def read_history(db, account_id, now, *, day_count=HISTORY_DAYS, include_benchmark=False):
    """Keep one saved observation per UTC day, with explicit missing days."""
    now = now.astimezone(UTC)
    today = now.date()
    start = today - timedelta(days=day_count - 1)
    postgres = db.get_bind().dialect.name == "postgresql"
    projection = "SELECT * FROM selected ORDER BY day"
    params = {"max_bytes": MAX_SNAPSHOT_BYTES}
    if postgres:
        projection = _POSTGRES_PROJECTION.format(
            benchmark_projection=_VUAG_PROJECTION if include_benchmark else ""
        )
        if include_benchmark:
            params["vuag_ticker"] = _VUAG_TICKER
    points = []
    days = (start + timedelta(days=index) for index in range(day_count))
    for row in _daily_snapshots(db, account_id, now, days, projection, params):
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
                        if include_benchmark and (
                            mark := _vuag_mark(fields, postgres, observed_at)
                        ):
                            point["vuag_mark"] = mark
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
