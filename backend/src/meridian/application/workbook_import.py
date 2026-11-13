"""Atomic acceptance of historical Excel observations into immutable evidence."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meridian.adapters.workbook_baseline import (
    MAX_BYTES,
    WorkbookBaselineError,
    WorkbookBaselineLayout,
    parse_workbook_baseline,
)
from meridian.application.imports import ImportReport, ImportStorageError, ImportValidationError
from meridian.persistence.models import Account, AuditRecord, ImportRun, SourceRecord

SOURCE_KIND = "excel_migration"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _accepted(session: Session, account_id: str, digest: str | None) -> bool:
    if digest is None:
        return False
    return (
        session.scalar(
            select(ImportRun.id)
            .where(
                ImportRun.account_id == account_id,
                ImportRun.kind == SOURCE_KIND,
                ImportRun.content_hash == digest,
                ImportRun.status == "succeeded",
            )
            .limit(1)
        )
        is not None
    )


def import_workbook_baseline(
    engine: Engine,
    *,
    account_id: str,
    content: bytes,
    layout: WorkbookBaselineLayout,
    currency: str = "GBP",
    actor: str = "local-admin",
    clock=lambda: datetime.now(UTC),
) -> ImportReport:
    """Keep a durable attempt, then accept all six source rows and audit together.

    This adds historical observations and zero economic events. Identical source
    bytes are idempotent per account. New workbook versions append new evidence.
    """
    if not isinstance(content, bytes):
        raise ImportValidationError("content_must_be_bytes")
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 64:
        raise ImportValidationError("invalid_actor")
    started = clock()
    if not isinstance(started, datetime) or started.utcoffset() is None:
        raise ImportValidationError("clock_must_be_aware")
    started = started.astimezone(UTC)
    digest = hashlib.sha256(content).hexdigest() if len(content) <= MAX_BYTES else None
    run_id = uuid4().hex
    counts = {
        "observations": 0,
        "source_records_added": 0,
        "economic_events_added": 0,
        "duplicate_files": 0,
        "rejected_files": 0,
    }
    try:
        with Session(engine) as session, session.begin():
            account = session.get(Account, account_id)
            if account is None:
                raise ImportValidationError("account_not_found")
            if currency != account.currency:
                raise ImportValidationError("account_currency_mismatch")
            duplicate = _accepted(session, account_id, digest)
            counts["duplicate_files"] = int(duplicate)
            session.add(
                ImportRun(
                    id=run_id,
                    account_id=account_id,
                    kind=SOURCE_KIND,
                    status="duplicate" if duplicate else "running",
                    content_hash=digest,
                    started_at=started,
                    finished_at=started if duplicate else None,
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

    error = None
    try:
        baseline = parse_workbook_baseline(content, layout=layout, currency=currency)
        sources = []
        for number, observation in enumerate(baseline.observations, 1):
            payload = _json(
                {
                    "record_type": "excel_baseline_observation",
                    "evidence_only": True,
                    "sheet": baseline.sheet,
                    "currency": currency,
                    "file_hash": digest,
                    "import_run": run_id,
                    "observation": observation,
                }
            )
            sources.append(
                SourceRecord(
                    id=uuid4().hex,
                    run_id=run_id,
                    account_id=account_id,
                    kind="excel_baseline_observation",
                    row_number=number,
                    schema_version=baseline.schema_version,
                    payload_json=payload,
                    digest=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                )
            )
        finished = clock()
        if not isinstance(finished, datetime) or finished.utcoffset() is None:
            raise ImportValidationError("clock_must_be_aware")
        with Session(engine) as session, session.begin():
            run = session.get(ImportRun, run_id)
            if run is None:
                raise ImportStorageError("import_log_unavailable")
            session.add_all(sources)
            counts["observations"] = counts["source_records_added"] = len(sources)
            run.status = "succeeded"
            run.finished_at = finished
            run.counts_json = _json(counts)
            session.add(
                AuditRecord(
                    id=uuid4().hex,
                    occurred_at=finished,
                    actor=actor,
                    action="excel_baseline_imported",
                    entity_type="import_run",
                    entity_id=run_id,
                    run_id=run_id,
                    details_json=_json({"counts": counts, "evidence_only": True}),
                )
            )
        return ImportReport(run_id, "succeeded", counts, None)
    except WorkbookBaselineError as exc:
        error = exc.code
    except IntegrityError:
        try:
            with Session(engine) as session:
                duplicate = _accepted(session, account_id, digest)
        except Exception:
            raise ImportStorageError("import_log_unavailable") from None
        error = "duplicate_file" if duplicate else "import_storage_failed"
    except Exception:
        error = "import_storage_failed"

    counts["observations"] = counts["source_records_added"] = 0
    duplicate = error == "duplicate_file"
    counts["duplicate_files"] = int(duplicate)
    counts["rejected_files"] = int(not duplicate)
    status = "duplicate" if duplicate else "failed"
    try:
        finished = clock()
        if not isinstance(finished, datetime) or finished.utcoffset() is None:
            finished = started
    except Exception:
        finished = started
    try:
        with Session(engine) as session, session.begin():
            run = session.get(ImportRun, run_id)
            if run is None:
                raise ImportStorageError("import_log_unavailable")
            run.status = status
            run.finished_at = finished
            run.error_code = error
            run.counts_json = _json(counts)
    except Exception:
        raise ImportStorageError("import_log_unavailable") from None
    return ImportReport(run_id, status, counts, error)
