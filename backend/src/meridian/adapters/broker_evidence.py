"""Validate captured broker evidence without interpreting cash/cost economics."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

FAMILIES = (
    "account_summary",
    "positions",
    "orders",
    "dividends",
    "transactions",
    "instruments",
    "exchanges",
)
MAX_CAPTURE_BYTES = 128 * 1024 * 1024


class EvidenceError(ValueError):
    """Safe code only; never include raw fields, identifiers or amounts."""


@dataclass(frozen=True)
class BrokerEvidence:
    document: dict = field(repr=False)
    content_hash: str = field(repr=False)
    broker_reference: str = field(repr=False)
    environment: str
    observed_from: datetime
    observed_to: datetime


def canonical(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("capture_duplicate_json_key")
        result[key] = value
    return result


def _invalid_number(_value):
    raise EvidenceError("capture_numeric_encoding_invalid")


def instant(value) -> datetime:
    try:
        if not isinstance(value, str):
            raise ValueError
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.utcoffset() is None:
            raise ValueError
        return result.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        raise EvidenceError("capture_timestamp_invalid") from None


def number(value) -> Decimal:
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int)) or len(str(value)) > 256:
            raise ValueError
        result = Decimal(value)
        if (
            not result.is_finite()
            or len(result.as_tuple().digits) > 128
            or abs(result.as_tuple().exponent) > 128
        ):
            raise ValueError
        return result
    except (ValueError, InvalidOperation):
        raise EvidenceError("capture_decimal_invalid") from None


def identifier(value) -> str:
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int))
        or not str(value).strip()
        or len(str(value)) > 256
    ):
        raise EvidenceError("capture_identity_invalid")
    return str(value)


def _no_credentials(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower().replace("-", "").replace("_", "") in {
                "authorization",
                "apikey",
                "apisecret",
                "accesstoken",
                "refreshtoken",
                "password",
            }:
                raise EvidenceError("capture_sensitive_field_rejected")
            _no_credentials(child)
    elif isinstance(value, list):
        for child in value:
            _no_credentials(child)


def validate_capture(content: bytes) -> BrokerEvidence:
    if not isinstance(content, bytes) or len(content) > MAX_CAPTURE_BYTES:
        raise EvidenceError("capture_size_invalid")
    try:
        doc = json.loads(
            content,
            object_pairs_hook=_object,
            parse_float=_invalid_number,
            parse_constant=_invalid_number,
        )
        _no_credentials(doc)
        if (
            type(doc["version"]) is not int
            or doc["version"] != 1
            or doc["source"] != "trading212_api_v0"
            or doc["numeric_encoding"] != "decimal_strings"
            or doc["environment"] not in ("demo", "live")
        ):
            raise EvidenceError("capture_contract_invalid")
        observations = doc["observations"]
        if set(observations) != set(FAMILIES):
            raise EvidenceError("capture_families_incomplete")
        starts, ends = [], []
        previous = None
        for family in FAMILIES:
            obs = observations[family]
            start, end = (
                instant(obs["retrieval_started_at"]),
                instant(obs["retrieval_completed_at"]),
            )
            if end < start or (previous is not None and start < previous):
                raise EvidenceError("capture_retrieval_order_invalid")
            previous = end
            starts.append(start)
            ends.append(end)
            if (
                obs["traversal_complete"] is not True
                or not isinstance(obs["records"], list)
                or any(not isinstance(row, dict) for row in obs["records"])
            ):
                raise EvidenceError("capture_family_invalid")
        summaries = observations["account_summary"]["records"]
        if len(summaries) != 1 or summaries[0]["currency"] != "GBP":
            raise EvidenceError("capture_account_invalid")
        reference = identifier(summaries[0]["id"])
        number(summaries[0]["totalValue"])
        number(summaries[0]["investments"]["currentValue"])
        positions = set()
        for row in observations["positions"]["records"]:
            ticker = identifier(row["instrument"]["ticker"])
            if ticker in positions:
                raise EvidenceError("capture_duplicate_position")
            positions.add(ticker)
            number(row["quantity"])
            if row.get("currentPrice") is not None:
                number(row["currentPrice"])
            wallet = row.get("walletImpact")
            if wallet:
                identifier(wallet["currency"])
                number(wallet["currentValue"])
        for family in ("orders", "dividends", "transactions"):
            identities = set()
            for row in observations[family]["records"]:
                if family == "orders":
                    order, fill = row["order"], row.get("fill")
                    identifier(order["id"])
                    identifier(order["instrument"]["ticker"])
                    if fill is None:
                        continue
                    identity = identifier(fill["id"])
                    number(fill["quantity"])
                    instant(fill["filledAt"])
                    identifier(fill["type"])
                    if fill.get("price") is not None:
                        number(fill["price"])
                else:
                    identity = identifier(row["reference"])
                    number(row["amount"])
                    identifier(row["currency"])
                    instant(row["paidOn" if family == "dividends" else "dateTime"])
                if identity in identities:
                    raise EvidenceError("capture_duplicate_event_identity")
                identities.add(identity)
        encoded = canonical(doc).encode()
        return BrokerEvidence(
            doc,
            hashlib.sha256(encoded).hexdigest(),
            reference,
            doc["environment"],
            min(starts),
            max(ends),
        )
    except EvidenceError:
        raise
    except Exception:
        raise EvidenceError("capture_contract_invalid") from None


def evidence_payloads(evidence: BrokerEvidence):
    """Per financial row; metadata arrays are retained once per generation."""
    observations = evidence.document["observations"]
    manifest = {key: value for key, value in evidence.document.items() if key != "observations"}
    manifest["observations"] = {
        family: {key: value for key, value in observations[family].items() if key != "records"}
        | {"record_count": len(observations[family]["records"])}
        for family in FAMILIES
    }
    yield "trading212_capture_manifest", canonical(manifest)
    for family in FAMILIES:
        observation = observations[family]
        context = {key: value for key, value in observation.items() if key != "records"}
        rows = (
            [observation["records"]]
            if family in ("instruments", "exchanges")
            else observation["records"]
        )
        for index, row in enumerate(rows, 1):
            yield (
                "trading212_" + family,
                canonical(
                    {
                        "evidence_only": True,
                        "environment": evidence.environment,
                        "family": family,
                        "record_index": index,
                        "context": context,
                        "raw": row,
                    }
                ),
            )
