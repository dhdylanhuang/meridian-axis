"""Bounded read of completed broker funding evidence for observed performance."""

import asyncio
import hashlib
import json

from sqlalchemy import LargeBinary, cast, func, select
from sqlalchemy.orm import Session

from meridian.adapters.broker_evidence import identifier, instant, number
from meridian.application.cutoff_pilot import read_pilot
from meridian.persistence.models import ImportRun, SourceRecord
from meridian.persistence.types import decimal_text

MAX_PAGES = 100
MAX_PAGE_BYTES = 128 * 1024
MAX_REQUEST_BYTES = 128 * 1024


class PerformanceUnavailable(RuntimeError):
    """Fixed private result codes for optional History enrichment."""


def performance_input(db, history):
    """Use the same complete provider traversal for coverage and transactions."""
    cutoff = instant(history["as_of"])
    start = instant(history["start_date"] + "T00:00:00Z")
    request = dict(days=history["days"], coverage=None, events=[])
    if "risk_range" in history:
        request["risk_range"] = history["risk_range"]
    run = db.scalar(
        select(ImportRun)
        .where(
            ImportRun.account_id == "shared-isa",
            ImportRun.kind == "trading212_history_transactions",
            ImportRun.status == "succeeded",
            ImportRun.finished_at <= cutoff,
        )
        .order_by(ImportRun.finished_at.desc(), ImportRun.id.desc())
        .limit(1)
    )
    if run is None:
        return request
    page_count = json.loads(run.counts_json).get("pages")
    if type(page_count) is not int or not 1 <= page_count <= MAX_PAGES:
        raise ValueError("funding_page_limit")
    payload_size = (
        func.octet_length(SourceRecord.payload_json)
        if db.get_bind().dialect.name == "postgresql"
        else func.length(cast(SourceRecord.payload_json, LargeBinary))
    )
    pages = db.scalars(
        select(SourceRecord)
        .where(
            SourceRecord.account_id == "shared-isa",
            SourceRecord.run_id == run.id,
            SourceRecord.kind == "trading212_history_page",
            payload_size <= MAX_PAGE_BYTES,
        )
        .order_by(SourceRecord.row_number)
        .limit(MAX_PAGES + 1)
    ).all()
    if len(pages) != page_count:
        raise ValueError("funding_pages_incomplete")
    seen = {}
    earliest = first_started = previous_end = None
    for index, page in enumerate(pages, start=1):
        encoded_page = page.payload_json.encode()
        if (
            page.row_number != index
            or len(encoded_page) > MAX_PAGE_BYTES
            or hashlib.sha256(encoded_page).hexdigest() != page.digest
        ):
            raise ValueError("funding_page_invalid")
        payload = json.loads(page.payload_json)
        records = payload["records"]
        started = instant(payload["retrieval_started_at"])
        ended = instant(payload["retrieval_completed_at"])
        continuation = payload["next_page_path"]
        if (
            payload["family"] != "transactions"
            or not isinstance(records, list)
            or len(records) > 50
            or not started <= ended <= run.finished_at
            or (previous_end is not None and started < previous_end)
            or (index == page_count and continuation is not None)
            or (index < page_count and (not isinstance(continuation, str) or not continuation))
        ):
            raise ValueError("funding_page_invalid")
        if first_started is None:
            first_started = started
        previous_end = ended
        for raw in records:
            reference = identifier(raw["reference"])
            at = instant(raw["dateTime"])
            if at > ended:
                raise ValueError("funding_timestamp_invalid")
            earliest = at if earliest is None else min(earliest, at)
            entry = dict(
                reference=reference,
                kind=identifier(raw["type"]),
                currency=identifier(raw["currency"]),
                amount=decimal_text(number(raw["amount"])),
                at=at.isoformat(),
            )
            if reference in seen and seen[reference] != entry:
                raise ValueError("funding_reference_conflict")
            seen[reference] = entry
    if earliest is not None and earliest <= first_started:
        request["coverage"] = dict(
            start_at=earliest.isoformat(),
            end_at=first_started.isoformat(),
            completed_at=run.finished_at.isoformat(),
        )
    # The first account capture can precede its saved UTC date by a day.
    opening = next(
        (instant(day["captured_at"]) for day in history["days"] if day["status"] == "observed"),
        start,
    )
    request["events"] = [
        entry for entry in seen.values() if instant(entry["at"]) >= min(start, opening)
    ]
    return request


async def performance_report(engine, history, calculate):
    if (
        not isinstance(history, dict)
        or history.get("source") != "trading212"
        or history.get("basis") != "broker_reported"
        or history.get("currency") != "GBP"
        or not isinstance(history.get("days"), list)
        or not 90 <= len(history["days"]) <= 367
    ):
        raise ValueError("performance_history_invalid")
    pilot = None
    try:
        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                connection.exec_driver_sql(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                connection.exec_driver_sql("SET LOCAL statement_timeout = '2s'")
            else:
                connection.exec_driver_sql("BEGIN")
            with Session(bind=connection) as db:
                value = performance_input(db, history)
                if "risk_range" in history:
                    try:
                        with db.begin_nested():
                            pilot = read_pilot(db, history["as_of"], value["coverage"])
                    except Exception:
                        pilot = {"state": "unavailable"}
            connection.rollback()
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode()) > MAX_REQUEST_BYTES:
            raise ValueError("performance_input_limit")
    except Exception:
        raise PerformanceUnavailable("funding_evidence_unavailable") from None
    try:
        async with asyncio.timeout(4):
            result = await calculate(encoded)
    except TimeoutError:
        raise PerformanceUnavailable("calculation_timeout") from None
    except Exception:
        raise PerformanceUnavailable("calculation_unavailable") from None
    if pilot is not None and isinstance(result, str) and len(result.encode()) <= MAX_REQUEST_BYTES:
        try:
            report = json.loads(result)
            if isinstance(report.get("metrics"), dict):
                report["metrics"]["cutoff_pilot"] = pilot
                enriched = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
                if len(enriched.encode()) <= MAX_REQUEST_BYTES:
                    result = enriched
        except (ValueError, AttributeError):
            pass
    if not isinstance(result, str) or len(result.encode()) > MAX_REQUEST_BYTES:
        raise PerformanceUnavailable("calculation_response_invalid")
    return result
