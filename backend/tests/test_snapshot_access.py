"""Synthetic snapshot publication, authorization and restricted-role reads."""

import asyncio
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_broker_ingestion import capture_document, encoded
from test_postgres import postgres_engine as postgres_engine
from test_postgres import postgres_schema as postgres_schema
from test_session_http import KEY, Provider
from test_sessions import NOW, ORIGIN, SUBJECTS
from test_sessions import engine as engine
from test_supabase_migration import native_engine as native_engine

from meridian.adapters.broker_evidence import validate_capture
from meridian.app import create_app
from meridian.application.broker_ingestion import ingest_capture
from meridian.application.snapshot_access import read_snapshot
from meridian.application.snapshot_publish import publish_snapshot
from meridian.persistence.models import Account, AccountMember, BrokerSnapshot
from meridian.security.http import SESSION_COOKIE, SessionHttp
from meridian.security.sessions import SessionService
from meridian.security.supabase_auth import VerifiedIdentity


def seed(dbengine):
    with Session(dbengine) as db, db.begin():
        account = db.get(Account, "shared-isa")
        if account is None:
            db.add(Account(id="shared-isa", environment="live"))
        else:
            account.environment = "live"
    report = ingest_capture(
        dbengine,
        account_id="shared-isa",
        content=encoded(),
        environment="live",
        expected_broker_reference="synthetic-broker",
        bind_unset_reference=True,
        clock=lambda: NOW,
    )
    assert report.status == "succeeded"
    with Session(dbengine) as db, db.begin():
        row = publish_snapshot(
            db,
            account_id="shared-isa",
            run_id=report.run_id,
            evidence=validate_capture(encoded()),
            now=NOW,
        )
        assert (
            publish_snapshot(
                db,
                account_id="shared-isa",
                run_id=report.run_id,
                evidence=validate_capture(encoded()),
                now=NOW,
            ).id
            == row.id
        )
    return report


def test_snapshot_projection_read_and_tamper_denial(engine):
    seed(engine)
    with Session(engine) as db:
        assert (
            read_snapshot(db, "shared-isa")["total_value"]
            == capture_document()["observations"]["account_summary"]["records"][0]["totalValue"]
        )
        assert read_snapshot(db, "other-account") is None
    with engine.begin() as c:
        c.execute(text("UPDATE broker_snapshots SET digest=:digest"), {"digest": "a" * 64})
    with Session(engine) as db, pytest.raises(RuntimeError, match="integrity_failed"):
        read_snapshot(db, "shared-isa")


def test_authenticated_snapshot_both_users_and_revocation(engine):
    seed(engine)
    with Session(engine) as db, db.begin():
        for slot, subject in enumerate(SUBJECTS, 1):
            db.add(
                AccountMember(
                    account_id="shared-isa", auth_subject=subject, slot=slot, created_at=NOW
                )
            )
    service = SessionService("shared-isa", ORIGIN)

    async def allowed():
        return True

    handler = SessionHttp(
        service, Provider(), lambda: Session(engine), allowed, KEY, clock=lambda: NOW
    )
    app = create_app(session_http=handler)
    tokens = []
    with Session(engine) as db, db.begin():
        for subject in SUBJECTS:
            tokens.append(
                service.issue(
                    db, VerifiedIdentity(subject, NOW + timedelta(minutes=5)), now=NOW
                ).token.get_secret_value()
            )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN
        ) as client:
            url = "/api/v1/portfolio/snapshot"
            assert (await client.get(url)).status_code == 401
            for token in tokens:
                response = await client.get(url, headers={"cookie": SESSION_COOKIE + "=" + token})
                assert response.status_code == 200 and response.json()["basis"] == "broker_reported"
                assert response.headers["cache-control"] == "no-store"
                assert "synthetic-broker" not in response.text
                assert (
                    await client.get(
                        url,
                        headers={
                            "cookie": SESSION_COOKIE + "=" + token,
                            "Origin": "https://foreign.invalid",
                        },
                    )
                ).status_code == 403
            assert (await client.post(url)).status_code == 405
            assert (
                await client.get(
                    url + "?account=other", headers={"cookie": SESSION_COOKIE + "=" + tokens[0]}
                )
            ).status_code == 403
            with Session(engine) as db, db.begin():
                db.get(AccountMember, ("shared-isa", SUBJECTS[0])).revoked_at = NOW
            assert (
                await client.get(url, headers={"cookie": SESSION_COOKIE + "=" + tokens[0]})
            ).status_code == 401

    asyncio.run(run())


@pytest.fixture(params=["postgres_engine", "native_engine"])
def runtime(request):
    e = request.getfixturevalue(request.param)
    with e.connect() as c:
        schema = c.scalar(text("SELECT current_schema()"))
    seed(e)
    return e, "meridian_bff_" + schema


@pytest.mark.postgres
def test_snapshot_restricted_role_select_only_and_foreign_scope(runtime):
    engine, role = runtime
    with Session(engine) as db, db.begin():
        snapshot = db.scalars(select(BrokerSnapshot)).one()
        # Foreign row satisfies its source/account FK but is invisible to runtime.
        from meridian.persistence.models import ImportRun

        db.add(Account(id="foreign", environment="live"))
        db.flush()
        db.add(
            ImportRun(
                id="foreign-run",
                account_id="foreign",
                kind="trading212_capture",
                status="succeeded",
                started_at=NOW,
            )
        )
        db.flush()
        db.add(
            BrokerSnapshot(
                id="foreign",
                account_id="foreign",
                source_run_id="foreign-run",
                observed_at=NOW,
                created_at=NOW,
                snapshot_json=snapshot.snapshot_json,
                digest=snapshot.digest,
            )
        )
    with Session(engine) as db, db.begin():
        db.execute(text(f'SET LOCAL ROLE "{role}"'))
        assert len(db.scalars(select(BrokerSnapshot)).all()) == 1
        assert read_snapshot(db, "shared-isa")["basis"] == "broker_reported"
        assert read_snapshot(db, "foreign") is None
    for sql in [
        "SELECT * FROM source_records",
        "SELECT * FROM import_log",
        "UPDATE broker_snapshots SET digest=repeat('b',64)",
        "DELETE FROM broker_snapshots",
        "INSERT INTO broker_snapshots DEFAULT VALUES",
    ]:
        with pytest.raises(DBAPIError) as caught, engine.begin() as c:
            c.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
            c.exec_driver_sql(sql)
        assert caught.value.orig.args[0]["C"] == "42501"


def test_old_capture_published_later_does_not_replace_newest_observation(engine):
    seed(engine)
    document = capture_document()
    for family in document["observations"].values():
        family["retrieval_started_at"] = "2025-01-01T00:00:00Z"
        family["retrieval_completed_at"] = "2025-01-01T00:00:00Z"
    document["observations"]["account_summary"]["records"][0]["totalValue"] = "1"
    from meridian.adapters.broker_evidence import canonical

    evidence = validate_capture(canonical(document).encode())
    report = ingest_capture(
        engine,
        account_id="shared-isa",
        content=canonical(document).encode(),
        environment="live",
        expected_broker_reference="synthetic-broker",
        clock=lambda: NOW + timedelta(days=1),
    )
    assert report.status == "succeeded"
    with Session(engine) as db, db.begin():
        publish_snapshot(
            db,
            account_id="shared-isa",
            run_id=report.run_id,
            evidence=evidence,
            now=NOW + timedelta(days=1),
        )
        assert read_snapshot(db, "shared-isa")["total_value"] != "1"


@pytest.mark.postgres
@pytest.mark.parametrize("path", ["alembic", "native"])
def test_0005_upgrade_preserves_source_and_adds_closed_snapshot_model(postgres_schema, path):
    from test_supabase_migration import SQL_PATHS, _execute_native_asset

    from meridian.persistence.postgres import upgrade_postgres_database

    if path == "alembic":
        upgrade_postgres_database(postgres_schema, revision="0005")
    else:
        _execute_native_asset(postgres_schema, paths=SQL_PATHS[:4])
    with Session(postgres_schema) as db, db.begin():
        db.add(
            Account(
                id="preserved", environment="demo", private_reference="synthetic-private-reference"
            )
        )
    if path == "alembic":
        upgrade_postgres_database(postgres_schema)
    else:
        _execute_native_asset(postgres_schema, paths=SQL_PATHS[4:])
    with Session(postgres_schema) as db:
        assert db.get(Account, "preserved").private_reference == "synthetic-private-reference"
        assert db.scalars(select(BrokerSnapshot)).all() == []
