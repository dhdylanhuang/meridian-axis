import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from meridian.adapters.trading212 import BrokerError
from meridian.broker_capture import MAGIC, capture
from meridian.recovery import RecoveryError, create_key, read_key


def reader():
    api = SimpleNamespace(environment="demo")
    api.account_summary = AsyncMock(
        return_value=SimpleNamespace(
            currency="GBP",
            raw_payload={
                "id": "synthetic-account",
                "totalValue": Decimal("0.123456789012345678901"),
            },
        )
    )
    for name in (
        "positions",
        "order_history",
        "dividend_history",
        "transaction_history",
        "instruments",
        "exchanges",
    ):
        setattr(api, name, AsyncMock(return_value=[]))
    return api


def test_capture_encrypts_exact_observations_and_exposes_only_safe_status(tmp_path):
    api = reader()
    key_file = tmp_path / "key"
    create_key(key_file)
    destination = tmp_path / "capture"
    result = asyncio.run(capture(api, destination, key_file))
    assert result["families_complete"] == 7
    assert result["ledger_imported"] is False
    assert "synthetic-account" not in json.dumps(result)
    data = destination.read_bytes()
    assert b"synthetic-account" not in data
    offset = len(MAGIC)
    decoded = json.loads(
        AESGCM(read_key(key_file)).decrypt(data[offset : offset + 12], data[offset + 12 :], MAGIC)
    )
    assert (
        decoded["observations"]["account_summary"]["records"][0]["totalValue"]
        == "0.123456789012345678901"
    )
    assert decoded["historical_lifetime_coverage"] == "unverified"
    assert decoded["snapshot_atomicity"] == "separate_requests_not_provider_atomic"
    assert decoded["observations"]["positions"]["traversal_complete"] is True


def test_late_history_failure_never_publishes_partial_capture(tmp_path):
    api = reader()
    api.dividend_history.side_effect = RuntimeError("synthetic-private-provider-body")
    key_file = tmp_path / "key"
    create_key(key_file)
    destination = tmp_path / "capture"
    with pytest.raises(RuntimeError):
        asyncio.run(capture(api, destination, key_file))
    assert not destination.exists()
    api.transaction_history.assert_not_called()


def test_wrong_account_currency_stops_before_fetching_holdings(tmp_path):
    api = reader()
    api.account_summary.return_value.currency = "USD"
    key_file = tmp_path / "key"
    create_key(key_file)
    with pytest.raises(BrokerError, match="account_currency_mismatch"):
        asyncio.run(capture(api, tmp_path / "capture", key_file))
    api.positions.assert_not_called()


def test_existing_destination_prevents_any_broker_request(tmp_path):
    api = reader()
    destination = tmp_path / "capture"
    destination.write_bytes(b"existing evidence")
    with pytest.raises(RecoveryError, match="destination_exists"):
        asyncio.run(capture(api, destination, tmp_path / "missing-key"))
    api.account_summary.assert_not_called()
    assert destination.read_bytes() == b"existing evidence"


def test_hidden_credentials_require_terminal(tmp_path, monkeypatch, capsys):
    import sys

    from meridian import broker_capture

    key_file = tmp_path / "key"
    create_key(key_file)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "broker_capture",
            "--prompt-credentials",
            "--key-file",
            str(key_file),
            str(tmp_path / "capture"),
        ],
    )
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    prompt = AsyncMock()
    monkeypatch.setattr(broker_capture.getpass, "getpass", prompt)
    with pytest.raises(SystemExit):
        broker_capture.main()
    assert "interactive_terminal_required" in capsys.readouterr().out
    prompt.assert_not_called()
