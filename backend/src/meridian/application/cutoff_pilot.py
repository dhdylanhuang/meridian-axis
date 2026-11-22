"""Store and read bounded, provisional broker account observations."""

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian.adapters.broker_evidence import canonical, instant, number
from meridian.persistence.models import ImportRun, SourceRecord
from meridian.persistence.types import decimal_text

FIRST = date(2026, 11, 23)
CALENDAR_REVIEWED_THROUGH = date(2028, 12, 31)
# London Stock Exchange business-day calendar. Half-days remain trading dates.
CLOSED_DATES = frozenset(
    map(
        date.fromisoformat,
        (
            "2026-12-25",
            "2026-12-28",
            "2027-01-01",
            "2027-03-26",
            "2027-03-29",
            "2027-05-03",
            "2027-05-31",
            "2027-08-30",
            "2027-12-27",
            "2027-12-28",
            "2028-01-03",
            "2028-04-14",
            "2028-04-17",
            "2028-05-01",
            "2028-05-29",
            "2028-08-28",
            "2028-12-25",
            "2028-12-26",
        ),
    )
)
TARGET = time(22, tzinfo=UTC)
WINDOW = timedelta(minutes=2)
SCHEMA = "trading212_account_cutoff_pilot_v1"
KIND = "trading212_refresh"
ACCOUNT = "shared-isa"


def _scheduled(day):
    return day >= FIRST and day.weekday() < 5 and day not in CLOSED_DATES


def targets(start, end):
    start = max(start, FIRST)
    for index in range((end - start).days + 1):
        day = start + timedelta(days=index)
        if _scheduled(day):
            yield datetime.combine(day, TARGET)


def target_at(now):
    now = now.astimezone(UTC)
    target = datetime.combine(now.date(), TARGET)
    if _scheduled(now.date()) and target <= now < target + WINDOW:
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
        if engine.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
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


def read_pilot(db, as_of, coverage, selection=None):
    now = instant(as_of)
    today = now.date()
    start = date.fromisoformat(selection["start"]) if selection else today - timedelta(days=89)
    end = date.fromisoformat(selection["end"]) if selection else today
    if not start < end <= today or (today - start).days > 366:
        raise ValueError("cutoff_report_range_invalid")
    preview_end = today + timedelta(days=14) if end == today else end
    expected = list(targets(start, preview_end))
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
        point = dict(
            date=target.date().isoformat(),
            target_at=target.isoformat(),
            status=state,
            calendar_reviewed=target.date() <= CALENDAR_REVIEWED_THROUGH,
        )
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
    return dict(
        source="trading212",
        basis="provisional_broker_capture",
        calendar_reviewed_through=CALENDAR_REVIEWED_THROUGH.isoformat(),
        observations=points,
    )
