"""Private holding marks on the same fixed 22:00 UTC grid as the ISA pilot."""

import hashlib
import json
import re
from datetime import timedelta
from decimal import localcontext

from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian.adapters.broker_evidence import canonical, instant, number
from meridian.application.cutoff_pilot import (
    ACCOUNT,
    CALENDAR_REVIEWED_THROUGH,
    KIND,
    WINDOW,
    _save,
    targets,
)
from meridian.persistence.models import SourceRecord
from meridian.persistence.types import decimal_text

SCHEMA = "trading212_holdings_cutoff_v1"
MAX_HOLDINGS = 128
MAX_RECORD = 64 * 1024
ISIN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")


def _id(target):
    return "isa-cutoff-holdings-" + target.date().isoformat()


def save_holdings(engine, target, started, captured, positions):
    if target is None or not target <= started <= captured < target + WINDOW:
        return
    try:
        rows = {}
        for position in positions:
            raw = position.raw_payload
            instrument = raw["instrument"]
            ticker = instrument["ticker"]
            if ticker in rows:
                raise ValueError("duplicate_holding")
            isin = instrument.get("isin")
            wallet = raw.get("walletImpact") or {}
            if (
                not isinstance(isin, str)
                or not ISIN.fullmatch(isin)
                or wallet.get("currency") != "GBP"
            ):
                continue
            if wallet.get("currentValue") is None or raw.get("quantity") is None:
                continue
            quantity = number(str(raw["quantity"]))
            value = number(str(wallet["currentValue"]))
            if quantity > 0 and value > 0:
                rows[ticker] = [isin, decimal_text(quantity), decimal_text(value)]
        if not rows or len(rows) > MAX_HOLDINGS:
            return
        row = dict(
            target_at=target.isoformat(),
            started_at=started.isoformat(),
            captured_at=captured.isoformat(),
            marks=rows,
        )
        if len(canonical(row).encode()) <= MAX_RECORD:
            _save(engine, _id(target), SCHEMA, started, captured, row)
    except Exception:
        print("cutoff_holdings_capture_unavailable")


def _valid_marks(record, target, as_of):
    if record is None:
        return {}
    payload, digest = record
    if len(payload.encode()) > MAX_RECORD or hashlib.sha256(payload.encode()).hexdigest() != digest:
        return {}
    try:
        row = json.loads(payload)
        started, captured = instant(row["started_at"]), instant(row["captured_at"])
        if (
            row["target_at"] == target.isoformat()
            and target <= started <= captured < target + WINDOW
            and captured <= as_of
            and isinstance(row["marks"], dict)
        ):
            return row["marks"]
    except (ValueError, TypeError, KeyError):
        pass
    return {}


def _level(mark, expected):
    try:
        isin, quantity, value = mark
        if isin != expected:
            return None
        quantity, value = number(quantity), number(value)
        if quantity > 0 and value > 0:
            with localcontext() as ctx:
                ctx.prec = 16
                return decimal_text(value / quantity)
    except (ValueError, TypeError, ArithmeticError):
        pass
    return None


def read_holdings(engine, request, *, now):
    holdings = request["holdings"]
    if (
        not isinstance(holdings, dict)
        or len(holdings) > MAX_HOLDINGS
        or any(
            not (
                isinstance(key, str)
                and 0 < len(key) <= 128
                and isinstance(isin, str)
                and ISIN.fullmatch(isin)
            )
            for key, isin in holdings.items()
        )
    ):
        raise ValueError("cutoff_holdings_request_invalid")
    # Only finished, calendar-reviewed slots. Include missing sessions so returns never bridge them.
    dates = [
        target
        for target in targets(now.date() - timedelta(days=366), now.date())
        if target.date() <= CALENDAR_REVIEWED_THROUGH and target + WINDOW <= now
    ][-253:]
    if not dates or not holdings:
        return {"dates": [], "levels": {}}
    ids = [_id(target) for target in dates]
    with Session(engine) as db:
        rows = db.execute(
            select(SourceRecord.run_id, SourceRecord.payload_json, SourceRecord.digest).where(
                SourceRecord.account_id == ACCOUNT,
                SourceRecord.run_id.in_(ids),
                SourceRecord.row_number == 1,
                SourceRecord.kind == KIND,
                SourceRecord.schema_version == SCHEMA,
            )
        )
        saved = {run_id: (payload, digest) for run_id, payload, digest in rows}
    levels = {ticker: [] for ticker in holdings}
    for target in dates:
        marks = _valid_marks(saved.get(_id(target)), target, now)
        for ticker, isin in holdings.items():
            levels[ticker].append(_level(marks.get(ticker), isin))
    return {"dates": [target.date().isoformat() for target in dates], "levels": levels}
