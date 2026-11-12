"""One-off read-only broker qualification, not a ledger import or scheduled sync.

Credentials come from the process environment or hidden interactive prompts.
Output is encrypted private observation evidence; terminal output has no amounts,
identifiers, source records or credentials. Every required family must succeed.
"""

import argparse
import asyncio
import getpass
import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from meridian.adapters.trading212 import BrokerError, Trading212Client
from meridian.recovery import MAX_BYTES, RecoveryError, private_write, read_key

MAGIC = b"MERIDIAN-BROKER-OBSERVATIONS-1\n"


def decimal_json(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError


async def observe(api: Trading212Client, *, timeout_seconds: float = 300) -> dict:
    """A complete traversal is distinct from complete account lifetime coverage."""
    result = {
        "version": 1,
        "environment": api.environment,
        "source": "trading212_api_v0",
        "account_wrapper": "owner_confirmed_isa_not_verified_by_summary_schema",
        "historical_lifetime_coverage": "unverified",
        "ledger_reconciled": False,
        "numeric_encoding": "decimal_strings",
        "observations": {},
    }
    async with asyncio.timeout(timeout_seconds):
        for family, method in (
            ("account_summary", api.account_summary),
            ("positions", api.positions),
            ("orders", api.order_history),
            ("dividends", api.dividend_history),
            ("transactions", api.transaction_history),
            ("instruments", api.instruments),
            ("exchanges", api.exchanges),
        ):
            started = datetime.now(UTC).isoformat()
            values = await method()
            if family == "account_summary":
                if values.currency != "GBP":
                    raise BrokerError("account_currency_mismatch")
                rows = [values]
            else:
                rows = values
            result["observations"][family] = {
                "retrieval_started_at": started,
                "retrieval_completed_at": datetime.now(UTC).isoformat(),
                "traversal_complete": True,
                "records": [row.raw_payload for row in rows],
            }
    result["quote_age"] = "unknown_provider_does_not_supply_quote_timestamp"
    result["snapshot_atomicity"] = "separate_requests_not_provider_atomic"
    return result


async def capture(api: Trading212Client, destination: Path, key_file: Path) -> dict:
    if destination.exists():
        raise RecoveryError("broker_destination_exists")
    key = read_key(key_file)
    observations = await observe(api)
    payload = json.dumps(observations, default=decimal_json, sort_keys=True).encode()
    if len(payload) > MAX_BYTES // 2:
        raise RecoveryError("broker_capture_size_limit")
    nonce = os.urandom(12)
    encrypted = MAGIC + nonce + AESGCM(key).encrypt(nonce, payload, MAGIC)
    private_write(destination, encrypted)
    return {
        "status": "observations_captured",
        "environment": api.environment,
        "families_complete": len(observations["observations"]),
        "historical_lifetime_coverage": "unverified",
        "ledger_imported": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("demo", "live"), default="demo")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--prompt-credentials", action="store_true")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        # No API call or credential prompt when private output/key is unsuitable.
        if args.destination.exists():
            raise RecoveryError("broker_destination_exists")
        read_key(args.key_file)
        key = os.environ.get("MERIDIAN_BROKER_API_KEY", "")
        secret = os.environ.get("MERIDIAN_BROKER_API_SECRET", "")
        if args.prompt_credentials:
            if not sys.stdin.isatty():
                raise BrokerError("interactive_terminal_required")
            key = getpass.getpass("Read-only Trading 212 API key (hidden): ")
            secret = getpass.getpass("Read-only Trading 212 API secret (hidden): ")

        async def execute():
            async with Trading212Client(
                api_key=key,
                api_secret=secret,
                environment=args.environment,
                max_pages=100,
                max_history_seconds=180,
            ) as api:
                return await capture(api, args.destination, args.key_file)

        print(json.dumps(asyncio.run(execute())))
    except Exception as error:
        if isinstance(error, BrokerError):
            category = error.code
        elif isinstance(error, RecoveryError):
            category = str(error)
        elif isinstance(error, TimeoutError):
            category = "broker_capture_timeout"
        else:
            category = "broker_capture_failed"
        print(json.dumps({"status": "failed", "category": category}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
