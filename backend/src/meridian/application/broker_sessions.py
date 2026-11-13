"""Use broker schedule instants, including breaks, holidays and half-days."""

from meridian.adapters.broker_evidence import instant


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
