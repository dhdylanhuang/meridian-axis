"""Read-only, generation-pinned drill-down behind the existing session authority."""

import asyncio
import hashlib
import json
import re
from decimal import Decimal

from sqlalchemy.orm import Session

from meridian.adapters.broker_evidence import canonical, identifier, instant
from meridian.application.cash_history import cash_history_request
from meridian.application.cash_reconciliation import (
    ACTIVITY_CATEGORIES,
    MAX_BYTES,
    MAX_EVENTS,
    _decimal_text,
)
from meridian.persistence.models import BrokerSnapshot


def activity_query(value):
    if not isinstance(value, dict) or set(value) != {
        "snapshot_id",
        "input_revision",
        "category",
        "currency",
        "offset",
        "limit",
    }:
        raise ValueError("request_invalid")
    identifier(value["snapshot_id"])
    if (
        not isinstance(value["input_revision"], str)
        or re.fullmatch(r"[0-9a-f]{64}", value["input_revision"]) is None
        or not isinstance(value["category"], str)
        or value["category"] not in ACTIVITY_CATEGORIES
        or not isinstance(value["currency"], str)
        or re.fullmatch(r"[A-Z]{3}", value["currency"]) is None
        or type(value["offset"]) is not int
        or not 0 <= value["offset"] <= MAX_EVENTS
        or type(value["limit"]) is not int
        or not 1 <= value["limit"] <= 50
    ):
        raise ValueError("request_invalid")
    return value


def validate_details(raw, query, request, expected_count):
    if not isinstance(raw, str) or len(raw.encode()) > 64 * 1024:
        raise ValueError("detail_result_invalid")
    result = json.loads(raw)
    if (
        not isinstance(result, dict)
        or set(result) != {"scope", "snapshot_id", "since", "cutoff", "details"}
        or result["scope"] != request["scope"]
        or result["snapshot_id"] != query["snapshot_id"]
        or result["since"] != request["activity_since"]
        or result["cutoff"] != request["cutoff"]
    ):
        raise ValueError("detail_result_invalid")
    details = result["details"]
    if (
        not isinstance(details, dict)
        or set(details) != {"category", "currency", "offset", "limit", "total_count", "entries"}
        or any(details[key] != query[key] for key in ("category", "currency", "offset", "limit"))
        or type(details["total_count"]) is not int
        or details["total_count"] != expected_count
        or not isinstance(details["entries"], list)
        or len(details["entries"]) != min(query["limit"], max(0, expected_count - query["offset"]))
    ):
        raise ValueError("detail_result_invalid")
    seen = set()
    for row in details["entries"]:
        if not isinstance(row, dict) or set(row) != {
            "family",
            "reference",
            "provider_type",
            "amount",
            "currency",
            "occurred_at",
            "instrument_label",
            "source_id",
            "revision_id",
            "revision",
            "digest",
        }:
            raise ValueError("detail_result_invalid")
        if (
            row["family"] != ("dividends" if query["category"] == "dividends" else "transactions")
            or row["currency"] != query["currency"]
            or type(row["revision"]) is not int
            or not 0 <= row["revision"] <= 2**32 - 1
            or not instant(request["activity_since"])
            <= instant(row["occurred_at"])
            <= instant(request["cutoff"])
            or not isinstance(row["digest"], str)
            or re.fullmatch(r"[0-9a-f]{64}", row["digest"]) is None
        ):
            raise ValueError("detail_result_invalid")
        for key in ("reference", "source_id", "provider_type"):
            identifier(row[key])
        if row["revision_id"] is not None:
            identifier(row["revision_id"])
        label = row["instrument_label"]
        if label is not None and (
            not isinstance(label, str)
            or not 0 < len(label.encode()) <= 512
            or any(ord(c) < 32 for c in label)
        ):
            raise ValueError("detail_result_invalid")
        _decimal_text(row["amount"])
        evidence = next(
            (
                source
                for source in request["observations"]
                if source["source_id"] == row["source_id"]
                and source["revision_id"] == row["revision_id"]
                and source["reference"] == row["reference"]
                and source.get("family", "transactions") == row["family"]
            ),
            None,
        )
        if (
            evidence is None
            or evidence["digest"] != row["digest"]
            or evidence["revision"] != row["revision"]
            or evidence["provider_type"] != row["provider_type"]
            or evidence["occurred_at"] != row["occurred_at"]
            or evidence["currency"] != row["currency"]
            or evidence.get("instrument_label") != label
            or Decimal(evidence["amount"]) != Decimal(row["amount"])
        ):
            raise ValueError("detail_result_invalid")
        key = (row["family"], row["reference"])
        if key in seen:
            raise ValueError("detail_result_invalid")
        seen.add(key)
    return {
        "snapshot_id": query["snapshot_id"],
        "input_revision": query["input_revision"],
        "since": result["since"],
        "cutoff": result["cutoff"],
        **details,
    }


async def cash_activity_page(engine, value, reconcile):
    query = activity_query(value)
    try:
        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                connection.exec_driver_sql(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                connection.exec_driver_sql("SET LOCAL statement_timeout = '2s'")
            else:
                connection.exec_driver_sql("BEGIN")
            with Session(bind=connection) as db:
                snapshot = db.get(BrokerSnapshot, query["snapshot_id"])
                if snapshot is None or snapshot.account_id != "shared-isa":
                    return {"error": "activity_snapshot_unavailable"}, 409
                if hashlib.sha256(snapshot.snapshot_json.encode()).hexdigest() != snapshot.digest:
                    raise ValueError("snapshot_integrity_invalid")
                projection = json.loads(snapshot.snapshot_json)
                summary = projection.get("cash_reconciliation", {})
                if (
                    not summary.get("activity_details_available")
                    or summary.get("input_revision") != query["input_revision"]
                ):
                    return {"error": "activity_generation_changed"}, 409
                total = next(
                    (
                        row
                        for row in summary["reported_activity"]["totals"]
                        if row["category"] == query["category"]
                        and row["currency"] == query["currency"]
                    ),
                    None,
                )
                if total is None:
                    raise ValueError("activity_category_unavailable")
                request = cash_history_request(
                    db,
                    account_id="shared-isa",
                    projection=projection,
                    snapshot_id=snapshot.id,
                    max_observations=MAX_EVENTS,
                    include_captures=False,
                    reported_activity=True,
                    pin_to_cutoff=True,
                    sign_policy="statement_checked_gbp_v1",
                )
            connection.rollback()
        # Pin every page to the exact inputs behind the clicked approved total.
        if hashlib.sha256(canonical(request).encode()).hexdigest() != query["input_revision"]:
            return {"error": "activity_generation_changed"}, 409
        request["detail_query"] = {
            key: query[key] for key in ("category", "currency", "offset", "limit")
        }
        encoded = canonical(request)
        if len(encoded.encode()) > MAX_BYTES:
            return {"error": "activity_limit"}, 503
        async with asyncio.timeout(4):
            raw = await reconcile(encoded)
        return validate_details(raw, query, request, total["event_count"]), 200
    except Exception:
        return {"error": "activity_unavailable"}, 503
