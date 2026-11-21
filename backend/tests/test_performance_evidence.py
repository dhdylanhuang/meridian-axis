"""Funding evidence and authenticated History use synthetic transactions only."""

import asyncio
import hashlib
import json
import os
from datetime import date, timedelta

import httpx
from sqlalchemy.orm import Session
from test_session_http import KEY, Provider
from test_sessions import NOW, ORIGIN, SUBJECTS
from test_sessions import engine as engine

from meridian.app import create_app
from meridian.application.performance_evidence import performance_input
from meridian.application.snapshot_access import read_history
from meridian.persistence.models import Account, AccountMember, ImportRun, SourceRecord
from meridian.security.http import SESSION_COOKIE, SessionHttp
from meridian.security.sessions import SessionService
from meridian.security.supabase_auth import VerifiedIdentity


def seed_history(db, run_id, *, complete):
    start = NOW - timedelta(minutes=5)
    rows = [
        dict(
            reference="opening",
            type="DEPOSIT",
            currency="GBP",
            amount="100",
            dateTime=(NOW - timedelta(days=300)).isoformat(),
        ),
        dict(
            reference="recent",
            type="WITHDRAW",
            currency="GBP",
            amount="-3.123456789",
            dateTime=(NOW - timedelta(hours=1)).isoformat(),
        ),
    ]
    db.add(
        ImportRun(
            id=run_id,
            account_id="shared-isa",
            kind="trading212_history_transactions",
            status="succeeded" if complete else "running",
            started_at=start,
            finished_at=(NOW - timedelta(minutes=1) if complete else None),
            counts_json='{"pages": 2}',
        )
    )
    db.flush()
    for index in range(2):
        started_at = start + timedelta(minutes=index)
        payload = json.dumps(
            dict(
                family="transactions",
                retrieval_started_at=started_at.isoformat(),
                retrieval_completed_at=(started_at + timedelta(seconds=5)).isoformat(),
                records=rows[:1] if index == 0 else rows,
                next_page_path="/synthetic/next" if index == 0 else None,
            )
        )
        db.add(
            SourceRecord(
                id=f"{run_id}-{index}",
                account_id="shared-isa",
                run_id=run_id,
                row_number=index + 1,
                kind="trading212_history_page",
                schema_version="synthetic",
                payload_json=payload,
                digest=hashlib.sha256(payload.encode()).hexdigest(),
            )
        )


def test_funding_coverage_requires_completed_traversal_and_fences_at_first_page(engine):
    with Session(engine) as db, db.begin():
        if db.get(Account, "shared-isa") is None:
            db.add(Account(id="shared-isa", environment="live"))
        seed_history(db, "running", complete=False)
    with Session(engine) as db, db.begin():
        history = read_history(db, "shared-isa", NOW)
        assert performance_input(db, history)["coverage"] is None
        seed_history(db, "complete", complete=True)
    with Session(engine) as db:
        request = performance_input(db, history)
        assert request["coverage"] == {
            "start_at": (NOW - timedelta(days=300)).isoformat(),
            "end_at": (NOW - timedelta(minutes=5)).isoformat(),
            "completed_at": (NOW - timedelta(minutes=1)).isoformat(),
        }
        assert [e["amount"] for e in request["events"]] == ["-3.123456789"]


def test_history_performance_keeps_public_window_and_fails_soft(engine):
    now = NOW.replace(month=11, day=20)
    service = SessionService("shared-isa", ORIGIN)
    with Session(engine) as db, db.begin():
        if db.get(Account, "shared-isa") is None:
            db.add(Account(id="shared-isa", environment="live"))
        db.add(
            AccountMember(account_id="shared-isa", auth_subject=SUBJECTS[0], slot=1, created_at=now)
        )
        db.flush()
        token = service.issue(
            db, VerifiedIdentity(SUBJECTS[0], now + timedelta(minutes=5)), now=now
        )
    calls = []

    async def allowed():
        return True

    async def performance(history):
        if "risk_range" in history:
            assert len(history["days"]) == 90
            return {"method": "modified_dietz_observed_v1", "drawdown": history["risk_range"]}
        assert history["start_date"] == "2025-12-31"
        assert history["end_date"] == "2026-11-20"
        assert len(history["days"]) > 90
        calls.append(history["as_of"])
        if len(calls) == 2:
            raise RuntimeError("synthetic failure")
        return {"method": "modified_dietz_observed_v1"}

    async def run():
        app = create_app(
            session_http=SessionHttp(
                service,
                Provider(),
                lambda: Session(engine),
                allowed,
                KEY,
                clock=lambda: now,
                performance=performance,
            )
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN
        ) as client:
            path = "/api/v1/portfolio/history"
            assert (await client.get(path)).status_code == 401 and not calls
            headers = {"Cookie": SESSION_COOKIE + "=" + token.token.get_secret_value()}
            for expected in ({"method": "modified_dietz_observed_v1"}, None):
                response = await client.get(path, headers=headers)
                assert response.status_code == 200
                assert response.headers["cache-control"] == "no-store"
                result = response.json()
                assert result["start_date"] == (now - timedelta(days=89)).date().isoformat()
                assert len(result["days"]) == 90
                assert result["performance"] == expected

            risk = "/api/v1/portfolio/risk"
            selected = {"start": "2026-11-18", "end": "2026-11-19"}
            url = risk + "?start=2026-11-18&end=2026-11-19"
            assert (await client.get(url)).status_code == 401
            response = await client.get(url, headers=headers)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.json()["range"] == response.json()["drawdown"] == selected
            assert "days" not in response.json()
            assert date.fromisoformat(response.json()["earliest_date"]) == now.date() - timedelta(
                days=366
            )
            for query in (
                "?account=foreign",
                "?start=2026-11-18&end=2026-11-21",
                "?start=2026-11-19&end=2026-11-18",
                "?start=2026-11-18&end=2026-11-19&end=2026-11-20",
            ):
                assert (await client.get(risk + query, headers=headers)).status_code == 400

    asyncio.run(run())


def test_session_funding_export_retains_boundary_and_never_overwrites(engine, tmp_path, capsys):
    from pathlib import Path
    from stat import S_IMODE

    from meridian.export_session_funding import main

    with Session(engine) as db, db.begin():
        db.add(Account(id="shared-isa", environment="live"))
        db.flush()
        seed_history(db, "complete", complete=True)
    output = tmp_path / "funding.json"
    arguments = [
        "--database",
        str(Path(engine.url.database)),
        "--start-at",
        (NOW - timedelta(hours=1)).isoformat(),
        "--end-at",
        (NOW - timedelta(minutes=5)).isoformat(),
        "--as-of",
        NOW.isoformat(),
        "--output",
        str(output),
    ]
    assert main(arguments) == 0
    if os.name == "posix":
        assert S_IMODE(output.stat().st_mode) == 0o600
    result = json.loads(output.read_bytes())
    assert result["coverage"]["start_at"] == (NOW - timedelta(hours=1)).isoformat()
    assert result["coverage"]["end_at"] == (NOW - timedelta(minutes=5)).isoformat()
    assert [event["amount"] for event in result["events"]] == ["-3.123456789"]
    assert json.loads(capsys.readouterr().out) == {
        "funding_window_available": True,
        "events_exported": 1,
    }
    assert main(arguments) == 2
    assert capsys.readouterr().err == "session_funding_export_failed\n"
    assert json.loads(output.read_bytes()) == result
