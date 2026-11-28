"""Private, bounded Trading 212 history projections for the portfolio export."""

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from sqlalchemy import LargeBinary, cast, func, select

from meridian.adapters.broker_evidence import identifier, instant, number
from meridian.application.performance_evidence import MAX_PAGE_BYTES, MAX_PAGES, performance_input
from meridian.persistence.models import ImportRun, SourceRecord
from meridian.persistence.types import decimal_text

ACCOUNT = "shared-isa"
LONDON = ZoneInfo("Europe/London")


def _history(db, family, now, identify, timestamp):
    run = db.scalar(
        select(ImportRun)
        .where(
            ImportRun.account_id == ACCOUNT,
            ImportRun.kind == f"trading212_history_{family}",
            ImportRun.status == "succeeded",
            ImportRun.finished_at <= now,
        )
        .order_by(ImportRun.finished_at.desc(), ImportRun.id.desc())
        .limit(1)
    )
    if run is None:
        return [], None
    count = json.loads(run.counts_json).get("pages")
    if type(count) is not int or not 1 <= count <= MAX_PAGES:
        raise ValueError("history_page_limit")
    size = (
        func.octet_length(SourceRecord.payload_json)
        if db.get_bind().dialect.name == "postgresql"
        else func.length(cast(SourceRecord.payload_json, LargeBinary))
    )
    pages = db.scalars(
        select(SourceRecord)
        .where(
            SourceRecord.account_id == ACCOUNT,
            SourceRecord.run_id == run.id,
            SourceRecord.kind == "trading212_history_page",
            size <= MAX_PAGE_BYTES,
        )
        .order_by(SourceRecord.row_number)
        .limit(MAX_PAGES + 1)
    ).all()
    if len(pages) != count:
        raise ValueError("history_pages_incomplete")
    seen, earliest, first, previous = {}, None, None, None
    for i, page in enumerate(pages, 1):
        if (
            page.row_number != i
            or hashlib.sha256(page.payload_json.encode()).hexdigest() != page.digest
        ):
            raise ValueError("history_page_invalid")
        body = json.loads(page.payload_json)
        start, end = instant(body["retrieval_started_at"]), instant(body["retrieval_completed_at"])
        continuation = body["next_page_path"]
        if (
            body["family"] != family
            or not isinstance(body["records"], list)
            or len(body["records"]) > 50
            or not start <= end <= run.finished_at
            or (previous and start < previous)
            or (i == count and continuation is not None)
            or (i < count and not isinstance(continuation, str))
        ):
            raise ValueError("history_page_invalid")
        first, previous = first or start, end
        for raw in body["records"]:
            at = timestamp(raw)
            if at > end:
                raise ValueError("history_timestamp_invalid")
            earliest = min(earliest, at) if earliest else at
            key = identify(raw)
            if key in seen and seen[key][1] != raw:
                raise ValueError("history_reference_conflict")
            seen[key] = (at, raw)
    return sorted(seen.values(), key=lambda item: item[0]), (earliest, first) if earliest else None


def _within(coverage, start, end):
    return (
        coverage is not None
        and start is not None
        and start < end
        and coverage[0] <= start <= end <= coverage[1]
    )


def _sum_flows(events, coverage, start, end):
    if not _within(coverage, start, end):
        return None
    relevant = [(at, item) for at, item in events if start < at <= end]
    if any(
        item["kind"]
        not in {
            "DEPOSIT",
            "WITHDRAW",
            "FEE",
            "INTEREST_FROM_CASH",
            "INTEREST_ON_CASH",
            "INTEREST_ON_FREE_CASH",
            "LENDING_INTEREST",
            "INTEREST",
        }
        or (
            item["kind"] in {"DEPOSIT", "WITHDRAW"}
            and (
                item["currency"] != "GBP"
                or (number(item["amount"]) < 0) != (item["kind"] == "WITHDRAW")
            )
        )
        for _, item in relevant
    ):
        return None
    return [
        (at, number(item["amount"]))
        for at, item in relevant
        if item["kind"] in {"DEPOSIT", "WITHDRAW"}
    ]


def allowance(flows):
    current = replaceable = Decimal(0)
    for _, amount in flows:
        if amount >= 0:
            replaced = min(amount, replaceable)
            replaceable -= replaced
            current += amount - replaced
        else:
            withdrawn = min(-amount, current)
            current -= withdrawn
            replaceable += -amount - withdrawn
    return {
        "net_subscriptions_gbp": decimal_text(current),
        "remaining_from_this_isa_only_gbp": decimal_text(max(Decimal(0), Decimal(20000) - current)),
        "prior_funds_replaceable_gbp": decimal_text(replaceable),
    }


def _tax_start(at):
    local = at.astimezone(LONDON).date()
    year = local.year - ((local.month, local.day) < (4, 6))
    return datetime(year, 4, 6, tzinfo=LONDON)


def export_history(db, value, now):
    end = instant(value["end"])
    start = instant(value["start"]) if value.get("start") else None
    weekly = [(key, instant(at)) for key, at in value.get("weekly", {}).items()]
    if (
        len(weekly) > 5
        or end > now
        or (start and start >= end)
        or any(at > end for _, at in weekly)
    ):
        raise ValueError("export_range_invalid")
    today = end.astimezone(LONDON).date()
    tax_start = _tax_start(now)
    anniversary = today.replace(year=today.year - 1, day=1)
    last_day = ((anniversary + timedelta(days=32)).replace(day=1) - timedelta(days=1)).day
    anniversary = anniversary.replace(day=min(today.day, last_day))
    trade_start = datetime.combine(anniversary, end.astimezone(LONDON).time(), tzinfo=LONDON)
    opening = value.get("turnover_open") or {}
    turnover_open = (
        instant(opening["account_captured_at"]) if opening.get("account_captured_at") else None
    )
    result = {
        "isa": {
            "tax_year_start": tax_start.date().isoformat(),
            "tax_year_end": (
                tax_start.date().replace(year=tax_start.year + 1) - timedelta(days=1)
            ).isoformat(),
            "limit_gbp": "20000",
            "as_of": end.isoformat(),
            "reason": "incomplete_or_unclassified_funding",
        },
        "monthly_net_deposits_gbp": None,
        "weekly_net_deposits_gbp": {},
        "trades": [],
        "trade_count": 0,
        "trade_coverage": "unavailable",
        "turnover_pct": None,
        "monthly_trade_activity": None,
        "monthly_dividends_gbp": None,
    }
    with localcontext() as ctx:
        ctx.prec = 80
        lower = min([tax_start, start or end, *(_tax_start(at) for _, at in weekly)])
        try:
            funding = performance_input(
                db,
                {
                    "as_of": now.isoformat(),
                    "start_date": (lower.date() - timedelta(days=1)).isoformat(),
                    "days": [],
                },
            )
            c = funding["coverage"]
            coverage = (instant(c["start_at"]), instant(c["end_at"])) if c else None
            events = sorted(
                ((instant(item["at"]), item) for item in funding["events"]),
                key=lambda item: item[0],
            )
            year_flows = _sum_flows(events, coverage, tax_start - timedelta(microseconds=1), end)
            if year_flows is not None:
                result["isa"].update(allowance(year_flows), reason=None)
            monthly = _sum_flows(events, coverage, start, end)
            if monthly is not None:
                result["monthly_net_deposits_gbp"] = decimal_text(
                    sum(amount for _, amount in monthly)
                )
            for key, at in weekly:
                flows = _sum_flows(events, coverage, _tax_start(at) - timedelta(microseconds=1), at)
                if flows is not None:
                    result["weekly_net_deposits_gbp"][key] = decimal_text(
                        sum(amount for _, amount in flows)
                    )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            result["isa"]["reason"] = "funding_evidence_invalid"
        try:
            rows, coverage = _history(
                db,
                "orders",
                now,
                lambda row: (
                    ("fill", identifier(row["fill"]["id"]))
                    if row.get("fill")
                    else ("order", identifier(row["order"]["id"]))
                ),
                lambda row: instant(
                    row["fill"]["filledAt"] if row.get("fill") else row["order"]["createdAt"]
                ),
            )
            changed, trades = set(), []
            for at, raw in rows:
                fill, order = raw.get("fill"), raw["order"]
                if not fill:
                    continue
                ticker = identifier(order.get("ticker") or order["instrument"]["ticker"])
                if start and start < at <= end:
                    changed.add(ticker)
                if not trade_start < at <= end or fill["type"] != "TRADE":
                    continue
                wallet = fill.get("walletImpact") or {}
                trades.append(
                    {
                        "at": at.isoformat(),
                        "ticker": ticker,
                        "side": order["side"],
                        "units": decimal_text(abs(number(fill["quantity"]))),
                        "price": fill.get("price"),
                        "currency": order.get("currency"),
                        "proceeds_gbp": wallet.get("netValue")
                        if wallet.get("currency") == "GBP"
                        else None,
                        "realised_pnl_gbp": wallet.get("realisedProfitLoss")
                        if wallet.get("currency") == "GBP" and order["side"] == "SELL"
                        else None,
                    }
                )
            result.update(
                trades=list(reversed(trades[-1000:])),
                trade_count=len(trades),
                trade_coverage="complete" if _within(coverage, trade_start, end) else "incomplete",
            )
            if _within(coverage, start, end):
                result["monthly_trade_activity"] = sorted(changed)
            if (
                _within(coverage, trade_start, end)
                and turnover_open
                and abs((turnover_open - trade_start).total_seconds()) <= 8 * 86400
                and all(row["proceeds_gbp"] is not None for row in trades)
            ):
                denominator = (
                    number(opening["invested_value"]) + number(value["securities_gbp"])
                ) / 2
                if denominator > 0:
                    turnover = (
                        100 * sum(abs(number(row["proceeds_gbp"])) for row in trades) / denominator
                    )
                    result["turnover_pct"] = decimal_text(turnover.quantize(Decimal("0.01")))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            pass
        try:
            rows, coverage = _history(
                db,
                "dividends",
                now,
                lambda row: identifier(row["reference"]),
                lambda row: instant(row["paidOn"]),
            )
            if _within(coverage, start, end):
                totals = defaultdict(Decimal)
                for at, row in rows:
                    if not start < at <= end:
                        continue
                    ticker = row.get("ticker") or (row.get("instrument") or {}).get("ticker")
                    if not ticker or row["currency"] != "GBP":
                        raise ValueError("dividend_identity_or_currency")
                    totals[ticker] += number(row["amount"])
                result["monthly_dividends_gbp"] = {
                    key: decimal_text(value) for key, value in totals.items()
                }
        except (KeyError, TypeError, ValueError, ArithmeticError):
            pass
    return result
