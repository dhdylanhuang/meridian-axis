"""Store and read bounded, provisional broker account observations."""

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from meridian.adapters.broker_evidence import canonical, instant, number
from meridian.persistence.models import ImportRun, SourceRecord
from meridian.persistence.types import decimal_text

FIRST = date(2026, 11, 23)
LAST = date(2026, 12, 4)
TARGET = time(22, tzinfo=UTC)
WINDOW = timedelta(minutes=2)
SCHEMA = "trading212_account_cutoff_pilot_v1"
KIND = "trading212_refresh"
ACCOUNT = "shared-isa"


def targets():
    for index in range((LAST - FIRST).days + 1):
        day = FIRST + timedelta(days=index)
        if day.weekday() < 5:
            yield datetime.combine(day, TARGET)


def target_at(now):
    now = now.astimezone(UTC)
    target = datetime.combine(now.date(), TARGET)
    if FIRST <= now.date() <= LAST and now.weekday() < 5 and target <= now < target + WINDOW:
        return target
    return None


def _run_id(target):
    return f"isa-cutoff-pilot-{target.date().isoformat()}"


def save_observation(engine, target, started, captured, total_value):
    if target is None or not target <= started <= captured < target + WINDOW:
        return
    try:
        value = decimal_text(number(str(total_value)))
        row = dict(
            target_at=target.isoformat(),
            started_at=started.isoformat(),
            captured_at=captured.isoformat(),
            total_value_gbp=value,
        )
        payload = canonical(row)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        run_id = _run_id(target)
        insert = postgres_insert if engine.dialect.name == "postgresql" else sqlite_insert
        with Session(engine) as db, db.begin():
            accepted = db.scalar(
                insert(ImportRun)
                .values(
                    id=run_id,
                    account_id=ACCOUNT,
                    kind=KIND,
                    status="succeeded",
                    started_at=started,
                    finished_at=captured,
                    content_hash=digest,
                )
                .on_conflict_do_nothing(index_elements=["id"])
                .returning(ImportRun.id)
            )
            if accepted:
                db.add(
                    SourceRecord(
                        id=run_id,
                        account_id=ACCOUNT,
                        run_id=run_id,
                        row_number=1,
                        kind=KIND,
                        schema_version=SCHEMA,
                        payload_json=payload,
                        digest=digest,
                    )
                )
    except Exception:
        # Auxiliary capture cannot fail the scheduled refresh/history path.
        print("cutoff_pilot_capture_unavailable")


def _checked_row(saved, target):
    if saved is None:
        return None
    payload, digest = saved
    if len(payload.encode()) > 2048 or hashlib.sha256(payload.encode()).hexdigest() != digest:
        return None
    try:
        row = json.loads(payload)
        started = instant(row["started_at"])
        captured = instant(row["captured_at"])
        value = number(row["total_value_gbp"])
        if (
            row["target_at"] == target.isoformat()
            and target <= started <= captured < target + WINDOW
        ):
            return (captured, decimal_text(value))
    except (ValueError, TypeError, KeyError):
        return None
    return None


def read_pilot(db, as_of, coverage):
    now = instant(as_of)
    expected = list(targets())
    ids = [_run_id(target) for target in expected if target <= now]
    saved = {}
    if ids:
        rows = db.execute(
            select(SourceRecord.run_id, SourceRecord.payload_json, SourceRecord.digest).where(
                SourceRecord.account_id == ACCOUNT,
                SourceRecord.run_id.in_(ids),
                SourceRecord.row_number == 1,
                SourceRecord.kind == KIND,
                SourceRecord.schema_version == SCHEMA,
            )
        )
        saved = {run_id: (payload, digest) for run_id, payload, digest in rows}

    window = None
    if coverage:
        window = (instant(coverage["start_at"]), instant(coverage["end_at"]))
    points = []
    previous = None
    for target in expected:
        stored = saved.get(_run_id(target))
        mark = _checked_row(stored, target)
        if mark and mark[0] > now:
            mark = None
        if mark:
            state = "observed"
        elif now < target + WINDOW:
            state = "pending"
        else:
            state = "unavailable" if stored else "missing"
        point = dict(date=target.date().isoformat(), target_at=target.isoformat(), status=state)
        if mark:
            captured, amount = mark
            point.update(
                captured_at=captured.isoformat(),
                total_value_gbp=amount,
                funding_coverage=(
                    "covered"
                    if window and window[0] <= previous < captured <= window[1]
                    else "unverified"
                )
                if previous
                else "no_previous_observation",
            )
        points.append(point)
        previous = mark[0] if mark else None
    return dict(source="trading212", basis="provisional_broker_capture", observations=points)
