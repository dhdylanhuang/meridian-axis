"""Finite read of the approved projection; no raw evidence or broker calls."""

import hashlib
import json

from sqlalchemy import select

from meridian.persistence.models import BrokerSnapshot

MAX_SNAPSHOT_BYTES = 512 * 1024


def read_snapshot(db, account_id):
    row = db.scalar(
        select(BrokerSnapshot)
        .where(BrokerSnapshot.account_id == account_id)
        .order_by(BrokerSnapshot.observed_at.desc(), BrokerSnapshot.id.desc())
        .limit(1)
    )
    if row is None:
        return None
    data = row.snapshot_json.encode()
    if len(data) > MAX_SNAPSHOT_BYTES or hashlib.sha256(data).hexdigest() != row.digest:
        raise RuntimeError("snapshot_integrity_failed")
    result = json.loads(data)
    if result.get("source") != "trading212" or result.get("basis") != "broker_reported":
        raise RuntimeError("snapshot_contract_invalid")
    return result
