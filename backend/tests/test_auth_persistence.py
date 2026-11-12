"""Closed membership/session constraints across both migration paths and dialects."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.exc import DBAPIError
from test_persistence import engine as engine
from test_postgres import postgres_engine as postgres_engine
from test_postgres import postgres_schema as postgres_schema
from test_supabase_migration import native_engine as native_engine

from meridian.persistence.models import Account, AccountMember, AppSession

NOW = datetime(2026, 1, 2, 12, tzinfo=UTC)
SUBJECTS = tuple(f"00000000-0000-4000-8000-{number:012d}" for number in range(1, 4))


@pytest.fixture(
    params=[
        "engine",
        pytest.param("postgres_engine", marks=pytest.mark.postgres),
        pytest.param("native_engine", marks=pytest.mark.postgres),
    ]
)
def auth_engine(request):
    return request.getfixturevalue(request.param)


def _member(subject=SUBJECTS[0], slot=1, account="synthetic-account"):
    return {"account_id": account, "auth_subject": subject, "slot": slot, "created_at": NOW}


def _seed(engine):
    with engine.begin() as connection:
        connection.execute(
            insert(Account),
            [
                {"id": "synthetic-account", "environment": "demo"},
                {"id": "other-account", "environment": "live"},
            ],
        )


def _session(**overrides):
    return {
        "token_hash": "a" * 64,
        "account_id": "synthetic-account",
        "auth_subject": SUBJECTS[0],
        "csrf_hash": "b" * 64,
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
    } | overrides


def test_two_active_slots_allow_replacement_without_erasing_revoked_members(auth_engine):
    _seed(auth_engine)
    with auth_engine.begin() as connection:
        connection.execute(insert(AccountMember), [_member(), _member(SUBJECTS[1], 2)])
    with pytest.raises(DBAPIError), auth_engine.begin() as connection:
        connection.execute(insert(AccountMember), _member(SUBJECTS[2], 1))
    with auth_engine.begin() as connection:
        connection.execute(
            update(AccountMember)
            .where(AccountMember.auth_subject == SUBJECTS[0])
            .values(revoked_at=NOW + timedelta(minutes=1))
        )
        connection.execute(insert(AccountMember), _member(SUBJECTS[2], 1))
    with auth_engine.connect() as connection:
        rows = connection.execute(select(AccountMember.slot, AccountMember.revoked_at)).all()
        assert len(rows) == 3
        assert sorted(slot for slot, revoked in rows if revoked is None) == [1, 2]
        assert [revoked for _, revoked in rows if revoked is not None] == [
            NOW + timedelta(minutes=1)
        ]


@pytest.mark.parametrize("slot", [0, 3])
def test_membership_rejects_slots_outside_two_equal_editors(auth_engine, slot):
    _seed(auth_engine)
    with pytest.raises(DBAPIError), auth_engine.begin() as connection:
        connection.execute(insert(AccountMember), _member(slot=slot))


def test_sessions_require_membership_for_the_same_account_and_subject(auth_engine):
    _seed(auth_engine)
    with auth_engine.begin() as connection:
        connection.execute(insert(AccountMember), _member())
        connection.execute(insert(AccountMember), _member(SUBJECTS[1], account="other-account"))
        connection.execute(insert(AppSession), _session())
    for overrides in ({"account_id": "other-account"}, {"auth_subject": SUBJECTS[2]}):
        with pytest.raises(DBAPIError), auth_engine.begin() as connection:
            connection.execute(insert(AppSession), _session(token_hash="c" * 64, **overrides))
    with auth_engine.connect() as connection:
        row = connection.execute(select(AppSession.created_at, AppSession.expires_at)).one()
        assert row == (NOW, NOW + timedelta(hours=1))


@pytest.mark.parametrize(
    "overrides",
    [
        {"token_hash": "short"},
        {"csrf_hash": "short"},
        {"expires_at": NOW},
        {"expires_at": NOW - timedelta(microseconds=1)},
    ],
)
def test_sessions_reject_invalid_hash_lengths_and_nonpositive_lifetime(auth_engine, overrides):
    _seed(auth_engine)
    with auth_engine.begin() as connection:
        connection.execute(insert(AccountMember), _member())
    with pytest.raises(DBAPIError), auth_engine.begin() as connection:
        connection.execute(insert(AppSession), _session(**overrides))
