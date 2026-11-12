"""Atomic acceptance of broker evidence. No economics or session-role grants."""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from meridian.adapters.broker_evidence import (
    MAX_CAPTURE_BYTES,
    BrokerEvidence,
    EvidenceError,
    canonical,
    evidence_payloads,
    identifier,
    validate_capture,
)
from meridian.application.broker_snapshot import broker_snapshot
from meridian.application.imports import (
    ImportReport,
    ImportStorageError,
    ImportValidationError,
    _finish_without_evidence,
)
from meridian.persistence.models import Account, AuditRecord, ImportRun, SourceRecord

KIND = "trading212_capture"


def _scope(account, environment, expected_reference, bind_unset_reference):
    if account is None:
        raise ImportValidationError("account_not_found")
    if (account.environment, account.broker, account.wrapper, account.currency) != (
        environment,
        "trading212",
        "isa",
        "GBP",
    ):
        raise ImportValidationError("broker_account_scope_mismatch")
    if account.private_reference != expected_reference and not (
        account.private_reference is None and bind_unset_reference
    ):
        raise ImportValidationError("broker_reference_binding_required")


def _accepted(session, account_id, digest):
    return (
        session.scalar(
            select(ImportRun.id)
            .where(
                ImportRun.account_id == account_id,
                ImportRun.kind == KIND,
                ImportRun.content_hash == digest,
                ImportRun.status == "succeeded",
            )
            .limit(1)
        )
        is not None
    )


def _sources(evidence: BrokerEvidence, account_id: str, run_id: str):
    for number, (kind, payload) in enumerate(evidence_payloads(evidence), 1):
        yield SourceRecord(
            id=uuid4().hex,
            account_id=account_id,
            run_id=run_id,
            kind=kind,
            row_number=number,
            schema_version="trading212_capture_v1",
            payload_json=payload,
            digest=hashlib.sha256(payload.encode()).hexdigest(),
        )


def ingest_capture(
    engine: Engine,
    *,
    account_id: str,
    content: bytes,
    environment: str,
    expected_broker_reference: str,
    bind_unset_reference: bool = False,
    actor: str = "administration",
    clock=lambda: datetime.now(UTC),
) -> ImportReport:
    """Trusted admin use after independent account-identity verification.

    First binding is explicit and commits only with complete evidence/audit. A
    new capture may repeat old broker events as new observations; it never adds
    economic events. Identical canonical captures cannot be accepted twice.
    Financial source differences do not block broker-observed snapshot use.
    """
    try:
        expected_broker_reference = identifier(expected_broker_reference)
    except EvidenceError:
        raise ImportValidationError("broker_reference_invalid") from None
    if environment not in ("demo", "live") or type(bind_unset_reference) is not bool:
        raise ImportValidationError("broker_context_invalid")
    if (
        not isinstance(actor, str)
        or not actor.strip()
        or len(actor) > 64
        or not isinstance(content, bytes)
    ):
        raise ImportValidationError("broker_context_invalid")
    stamp = clock()
    if not isinstance(stamp, datetime) or stamp.utcoffset() is None:
        raise ImportValidationError("clock_must_be_aware")
    stamp = stamp.astimezone(UTC)
    run_id = uuid4().hex
    counts = {
        "source_records_added": 0,
        "economic_events_added": 0,
        "duplicate_captures": 0,
        "rejected_captures": 0,
    }
    try:
        with Session(engine) as session, session.begin():
            _scope(
                session.get(Account, account_id),
                environment,
                expected_broker_reference,
                bind_unset_reference,
            )
            session.add(
                ImportRun(
                    id=run_id,
                    account_id=account_id,
                    kind=KIND,
                    status="running",
                    content_hash=hashlib.sha256(content).hexdigest()
                    if len(content) <= MAX_CAPTURE_BYTES
                    else None,
                    started_at=stamp,
                    counts_json=canonical(counts),
                )
            )
    except ImportValidationError:
        raise
    except Exception:
        raise ImportStorageError("import_log_unavailable") from None

    def finish(status, code):
        return _finish_without_evidence(
            engine, run_id=run_id, status=status, finished_at=stamp, error_code=code, counts=counts
        )

    try:
        evidence = validate_capture(content)
        if (
            evidence.environment != environment
            or evidence.broker_reference != expected_broker_reference
        ):
            raise EvidenceError("capture_account_identity_mismatch")
        broker_snapshot(evidence)  # All displayed optional numbers must also validate.
        sources = list(_sources(evidence, account_id, run_id))
    except EvidenceError as error:
        counts["rejected_captures"] = 1
        return finish("failed", str(error))
    except Exception:
        counts["rejected_captures"] = 1
        return finish("failed", "capture_validation_failed")
    try:
        with Session(engine) as session, session.begin():
            account = session.scalar(
                select(Account).where(Account.id == account_id).with_for_update()
            )
            _scope(account, environment, expected_broker_reference, bind_unset_reference)
            run = session.get(ImportRun, run_id)
            if run is None:
                raise ImportStorageError("import_log_unavailable")
            duplicate = _accepted(session, account_id, evidence.content_hash)
            if duplicate:
                counts["duplicate_captures"] = 1
                run.status = "duplicate"
                run.error_code = "duplicate_capture"
            else:
                binding_added = account.private_reference is None
                if binding_added:
                    account.private_reference = expected_broker_reference
                session.add_all(sources)
                counts["source_records_added"] = len(sources)
                run.status = "succeeded"
                session.add(
                    AuditRecord(
                        id=uuid4().hex,
                        occurred_at=stamp,
                        actor=actor,
                        action="broker_evidence_accepted",
                        entity_type="import_run",
                        entity_id=run_id,
                        run_id=run_id,
                        details_json=canonical(
                            {
                                "evidence_only": True,
                                "families_complete": 7,
                                "broker_reference_bound": binding_added,
                                "economic_events_added": 0,
                            }
                        ),
                    )
                )
            run.content_hash = evidence.content_hash
            run.finished_at = stamp
            run.counts_json = canonical(counts)
        return ImportReport(
            run_id,
            "duplicate" if duplicate else "succeeded",
            counts,
            "duplicate_capture" if duplicate else None,
        )
    except IntegrityError:
        try:
            with Session(engine) as session:
                duplicate = _accepted(session, account_id, evidence.content_hash)
        except Exception:
            raise ImportStorageError("import_log_unavailable") from None
        if duplicate:
            counts["source_records_added"] = 0
            counts["duplicate_captures"] = 1
            return finish("duplicate", "duplicate_capture")
    except Exception:
        pass
    counts["source_records_added"] = 0
    counts["rejected_captures"] = 1
    return finish("failed", "broker_evidence_storage_failed")
