"""Use broker schedule instants, including breaks, holidays and half-days."""

from meridian.adapters.broker_evidence import instant


def select_session_metadata(tickers, instruments, exchanges):
    """Retain original held-listing rows and their schedule facts with explicit scope."""
    tickers = set(tickers)
    selected = [row for row in instruments if row["ticker"] in tickers]
    schedules = {
        str(row["workingScheduleId"])
        for row in selected
        if row.get("workingScheduleId") is not None
    }
    selected_exchanges = []
    for exchange in exchanges:
        matching = [
            schedule
            for schedule in exchange["workingSchedules"]
            if str(schedule["id"]) in schedules
        ]
        if matching:
            selected_exchanges.append(dict(exchange, workingSchedules=matching))
    return dict(
        scope="held_listing_schedules",
        requested_tickers=sorted(tickers),
        missing_tickers=sorted(tickers - {row["ticker"] for row in selected}),
        instruments=selected,
        exchanges=selected_exchanges,
    )


def relevant_session(now, tickers, instruments, exchanges):
    """Return open/closed/unknown. Unknown coverage permits conservative polling."""
    if not tickers:
        return "unknown"
    listing_schedules = {row["ticker"]: str(row.get("workingScheduleId")) for row in instruments}
    schedules = {
        str(schedule["id"]): schedule.get("timeEvents", [])
        for exchange in exchanges
        for schedule in exchange.get("workingSchedules", [])
    }
    states = []
    for ticker in tickers:
        events = schedules.get(listing_schedules.get(ticker))
        if not events:
            states.append("unknown")
            continue
        try:
            ordered = sorted(
                (instant(e["date"]), e["type"])
                for e in events
                if e["type"] in {"OPEN", "CLOSE", "BREAK_START", "BREAK_END"}
            )
            before = [(stamp, kind) for stamp, kind in ordered if stamp <= now]
            after = [(stamp, kind) for stamp, kind in ordered if stamp > now]
            if not before or not after:
                states.append("unknown")
            else:
                states.append("open" if before[-1][1] in {"OPEN", "BREAK_END"} else "closed")
        except (KeyError, ValueError, TypeError):
            states.append("unknown")
    return "open" if "open" in states else "unknown" if "unknown" in states else "closed"
