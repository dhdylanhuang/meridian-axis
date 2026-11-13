"""Provider UTC instants preserve breaks, half-days, holidays and DST shifts."""

from datetime import UTC, datetime

from meridian.application.broker_sessions import relevant_session


def state(stamp, events):
    instruments = [{"ticker": "SYN", "workingScheduleId": 1}]
    exchanges = [
        {
            "workingSchedules": [
                {"id": 1, "timeEvents": [{"date": date, "type": kind} for date, kind in events]}
            ]
        }
    ]
    return relevant_session(
        datetime.fromisoformat(stamp).replace(tzinfo=UTC), ["SYN"], instruments, exchanges
    )


def test_regular_halfday_and_holiday_follow_provider_instants():
    events = [
        ("2026-11-12T08:00:00Z", "OPEN"),
        ("2026-11-12T12:00:00Z", "CLOSE"),
        ("2026-11-16T08:00:00Z", "OPEN"),
        ("2026-11-16T16:30:00Z", "CLOSE"),
    ]
    assert state("2026-11-12T09:00:00", events) == "open"
    assert state("2026-11-12T13:00:00", events) == "closed"
    assert state("2026-11-13T10:00:00", events) == "closed"
    assert state("2026-11-16T17:00:00", events) == "unknown"


def test_lunch_breaks_and_dst_are_explicit_instants():
    events = [
        ("2026-03-30T07:00:00Z", "OPEN"),
        ("2026-03-30T10:00:00Z", "BREAK_START"),
        ("2026-03-30T11:00:00Z", "BREAK_END"),
        ("2026-03-30T15:30:00Z", "CLOSE"),
    ]
    assert state("2026-03-30T07:30:00", events) == "open"
    assert state("2026-03-30T10:30:00", events) == "closed"
    assert state("2026-03-30T11:30:00", events) == "open"
    assert relevant_session(datetime.now(UTC), ["unmapped"], [], []) == "unknown"


def test_metadata_selection_keeps_exact_held_facts_without_full_catalogue_storage():
    from meridian.adapters.broker_evidence import canonical
    from meridian.application.broker_sessions import select_session_metadata

    held = {"ticker": "HELD", "workingScheduleId": 1, "currencyCode": "GBP", "name": "Synthetic"}
    unheld = {"ticker": "UNHELD", "workingScheduleId": 2, "padding": "x" * (5 * 1024 * 1024)}
    schedule = {"id": 1, "timeEvents": [{"date": "2026-11-13T08:00:00Z", "type": "OPEN"}]}
    exchange = {
        "id": 1,
        "name": "Synthetic exchange",
        "workingSchedules": [schedule, {"id": 2, "timeEvents": []}],
    }
    result = select_session_metadata(["HELD", "MISSING"], [held, unheld], [exchange])
    assert result["scope"] == "held_listing_schedules"
    assert result["missing_tickers"] == ["MISSING"]
    assert result["instruments"] == [held]
    assert result["exchanges"][0]["workingSchedules"] == [schedule]
    assert len(exchange["workingSchedules"]) == 2
    assert len(canonical(result).encode()) < 4096
