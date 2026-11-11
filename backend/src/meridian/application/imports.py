"""Atomic holdings-snapshot evidence import; no economic events are booked."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meridian.adapters.holdings_csv import (
    DEFAULT_MAX_BYTES,
    HoldingsCSVError,
    HoldingSnapshot,
    HoldingSnapshotRow,
    SnapshotControl,
    parse_holdings_csv,
)
from meridian.persistence.models import Account, AuditRecord, ImportRun, SourceRecord
from meridian.persistence.types import decimal_text

SOURCE_KIND = "holdings_snapshot"
Clock = Callable[[], datetime]


class ImportValidationError(ValueError):
    """Invalid administrative context; messages contain no supplied values."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ImportStorageError(RuntimeError):
    """The operation log could not be durably written; never report success."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ImportReport:
    run_id: str
    status: str
    counts: dict[str, int | None]
    safe_error: str | None


def _now() -> datetime:
    return datetime.now(UTC)


def _time(clock: Clock) -> datetime:
    instant = clock()
    if not isinstance(instant, datetime) or instant.utcoffset() is None:
        raise ImportValidationError("clock_must_be_aware")
    return instant.astimezone(UTC)


def _finish_time(clock: Clock, fallback: datetime) -> datetime:
    # Keep a failed attempt durable even if an injected/system clock fails after
    # the running record was created. The start is the last known valid instant.
    try:
        return _time(clock)
    except Exception:
        return fallback


def _counts() -> dict[str, int | None]:
    return {
        "rows_read": None,
        "holding_rows": 0,
        "control_rows": 0,
        "source_records_added": 0,
        "economic_events_added": 0,
        "duplicate_files": 0,
        "rejected_files": 0,
    }


def _json(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _accepted(session: Session, account_id: str, content_hash: str) -> bool:
    return (
        session.scalar(
            select(ImportRun.id)
            .where(
                ImportRun.account_id == account_id,
                ImportRun.kind == SOURCE_KIND,
                ImportRun.content_hash == content_hash,
                ImportRun.status == "succeeded",
            )
            .limit(1)
        )
        is not None
    )


def preview_holdings(
    content: bytes,
    *,
    currency: str,
    observed_at: datetime,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> HoldingSnapshot:
    """Validate the complete file without creating an operation or any evidence."""
    return parse_holdings_csv(
        content, currency=currency, observed_at=observed_at, max_bytes=max_bytes
    )


def _source_record(
    row: HoldingSnapshotRow | SnapshotControl,
    snapshot: HoldingSnapshot,
    *,
    run_id: str,
    account_id: str,
) -> SourceRecord:
    is_control = isinstance(row, SnapshotControl)
    normalized = {
        "invested_value": decimal_text(row.invested_value),
        "value": decimal_text(row.value),
        "result": decimal_text(row.result),
        "dividends_gained": (
            None if row.dividends_gained is None else decimal_text(row.dividends_gained)
        ),
        "dividends_cash": None if row.dividends_cash is None else decimal_text(row.dividends_cash),
        "dividends_reinvested": (
            None if row.dividends_reinvested is None else decimal_text(row.dividends_reinvested)
        ),
    }
    if isinstance(row, HoldingSnapshotRow):
        normalized |= {
            "ticker": row.ticker,
            "name": row.name,
            "owned_quantity": decimal_text(row.owned_quantity),
        }
    else:
        normalized["group_name"] = row.group_name
    kind = "holdings_snapshot_control" if is_control else "holdings_snapshot_row"
    payload = _json(
        {
            "record_type": kind,
            "evidence_only": True,
            "context": {
                "currency": snapshot.currency,
                "observed_at": snapshot.observed_at.isoformat(),
                "observation_time_basis": "caller_supplied",
                "group_label": snapshot.group_name,
                "schema_version": snapshot.schema_version,
            },
            "raw_fields": row.raw_fields,
            "raw_text": row.raw_text,
            "normalized": normalized,
        }
    )
    return SourceRecord(
        id=uuid4().hex,
        run_id=run_id,
        account_id=account_id,
        kind=kind,
        row_number=row.row_number,
        schema_version=snapshot.schema_version,
        payload_json=payload,
        digest=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


def _finish_without_evidence(
    engine: Engine,
    *,
    run_id: str,
    status: str,
    finished_at: datetime,
    error_code: str,
    counts: dict[str, int | None],
) -> ImportReport:
    try:
        with Session(engine) as session, session.begin():
            run = session.get(ImportRun, run_id)
            if run is None:
                raise ImportStorageError("import_log_unavailable")
            run.status = status
            run.finished_at = finished_at
            run.error_code = error_code
            run.counts_json = _json(counts)
    except Exception:
        raise ImportStorageError("import_log_unavailable") from None
    return ImportReport(run_id, status, counts, error_code)


def import_holdings(
    engine: Engine,
    *,
    account_id: str,
    content: bytes,
    currency: str,
    observed_at: datetime,
    actor: str = "local-admin",
    clock: Clock = _now,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> ImportReport:
    """Persist a complete validated snapshot or a failed/duplicate attempt.

    Account/currency mistakes fail before creating a scoped run. Parsing and
    payload construction happen outside write transactions. Only successful
    evidence, its audit and operation completion commit together. Raw exception
    messages never enter logs or the returned diagnostic.
    """
    if not isinstance(content, bytes):
        raise ImportValidationError("content_must_be_bytes")
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 64:
        raise ImportValidationError("invalid_actor")
    started_at = _time(clock)
    # A bounded caller may supply only max_bytes+1 bytes to signal oversize.
    # Never misrepresent that rejected prefix digest as the full source hash.
    content_hash = hashlib.sha256(content).hexdigest() if len(content) <= max_bytes else None
    run_id = uuid4().hex
    counts = _counts()
    try:
        with Session(engine) as session, session.begin():
            account = session.get(Account, account_id)
            if account is None:
                raise ImportValidationError("account_not_found")
            if currency != account.currency:
                raise ImportValidationError("account_currency_mismatch")
            duplicate = content_hash is not None and _accepted(session, account_id, content_hash)
            if duplicate:
                counts["duplicate_files"] = 1
            session.add(
                ImportRun(
                    id=run_id,
                    account_id=account_id,
                    kind=SOURCE_KIND,
                    status="duplicate" if duplicate else "running",
                    content_hash=content_hash,
                    started_at=started_at,
                    finished_at=started_at if duplicate else None,
                    error_code="duplicate_file" if duplicate else None,
                    counts_json=_json(counts),
                )
            )
    except ImportValidationError:
        raise
    except Exception:
        raise ImportStorageError("import_log_unavailable") from None
    if duplicate:
        return ImportReport(run_id, "duplicate", counts, "duplicate_file")

    try:
        snapshot = preview_holdings(
            content, currency=currency, observed_at=observed_at, max_bytes=max_bytes
        )
    except HoldingsCSVError as exc:
        counts["rejected_files"] = 1
        return _finish_without_evidence(
            engine,
            run_id=run_id,
            status="failed",
            finished_at=_finish_time(clock, started_at),
            error_code=exc.code,
            counts=counts,
        )
    except (TypeError, ValueError):
        counts["rejected_files"] = 1
        return _finish_without_evidence(
            engine,
            run_id=run_id,
            status="failed",
            finished_at=_finish_time(clock, started_at),
            error_code="invalid_import_context",
            counts=counts,
        )
    except Exception:
        counts["rejected_files"] = 1
        return _finish_without_evidence(
            engine,
            run_id=run_id,
            status="failed",
            finished_at=_finish_time(clock, started_at),
            error_code="import_parse_failed",
            counts=counts,
        )

    counts |= {
        "rows_read": len(snapshot.holdings) + 1,
        "holding_rows": len(snapshot.holdings),
        "control_rows": 1,
    }
    try:
        sources = [
            _source_record(row, snapshot, run_id=run_id, account_id=account_id)
            for row in (*snapshot.holdings, snapshot.control)
        ]
        finished_at = _time(clock)
        with Session(engine) as session, session.begin():
            run = session.get(ImportRun, run_id)
            if run is None:
                raise ImportStorageError("import_log_unavailable")
            session.add_all(sources)
            counts["source_records_added"] = len(sources)
            run.status = "succeeded"
            run.finished_at = finished_at
            run.counts_json = _json(counts)
            session.add(
                AuditRecord(
                    id=uuid4().hex,
                    occurred_at=finished_at,
                    actor=actor,
                    action="holdings_snapshot_imported",
                    entity_type="import_run",
                    entity_id=run_id,
                    run_id=run_id,
                    details_json=_json({"counts": counts, "evidence_only": True}),
                )
            )
        return ImportReport(run_id, "succeeded", counts, None)
    except IntegrityError:
        # Another accepted import may have won after the initial hash check.
        # Only classify this as a duplicate if that exact accepted scope exists.
        try:
            with Session(engine) as session:
                duplicate = content_hash is not None and _accepted(
                    session, account_id, content_hash
                )
        except Exception:
            raise ImportStorageError("import_log_unavailable") from None
        counts["source_records_added"] = 0
        if duplicate:
            counts["duplicate_files"] = 1
            return _finish_without_evidence(
                engine,
                run_id=run_id,
                status="duplicate",
                finished_at=_finish_time(clock, started_at),
                error_code="duplicate_file",
                counts=counts,
            )
    except Exception:
        # Error text can include raw payloads, filenames or values. Persist only
        # a stable safe category; successful partial writes already rolled back.
        pass

    counts["source_records_added"] = 0
    counts["rejected_files"] = 1
    return _finish_without_evidence(
        engine,
        run_id=run_id,
        status="failed",
        finished_at=_finish_time(clock, started_at),
        error_code="import_storage_failed",
        counts=counts,
    )
