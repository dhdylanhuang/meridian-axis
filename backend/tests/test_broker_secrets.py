"""Provisioning never puts broker secrets in argv, output or local files."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from meridian import broker_secrets


def test_secret_pair_goes_only_to_stdin_after_account_and_deployment_preflight(
    tmp_path, monkeypatch, capsys
):
    fake = tmp_path / "backend/src/meridian/broker_secrets.py"
    monkeypatch.setattr(broker_secrets, "__file__", str(fake))
    prototype = tmp_path / "prototype/worker-feasibility"
    executable = prototype / "node_modules/.bin/wrangler"
    executable.parent.mkdir(parents=True)
    executable.touch()
    (prototype / "wrangler.sync-runtime.template.json").write_text(
        json.dumps({"account_id": "synthetic-account"})
    )
    monkeypatch.setattr(broker_secrets.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(broker_secrets.sys.stderr, "isatty", lambda: True)
    prompt = Mock(side_effect=["synthetic-key", "synthetic-secret"])
    monkeypatch.setattr(broker_secrets.getpass, "getpass", prompt)
    calls = []

    def run(args, **options):
        calls.append((args, options))
        assert "synthetic-key" not in args and "synthetic-secret" not in args
        if args[1] == "whoami":
            assert prompt.call_count == 0
            return SimpleNamespace(
                returncode=0, stdout=b'{"accounts":[{"id":"synthetic-account"}]}'
            )
        if args[1] == "deployments":
            assert prompt.call_count == 0
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(broker_secrets.subprocess, "run", run)
    assert broker_secrets.main(["--confirm-read-only"]) == 0
    args, options = calls[-1]
    assert args[1:] == ["secret", "bulk", "--name", "meridian-axis-sync-runtime"]
    assert json.loads(options["input"]) == {
        "BROKER_API_KEY": "synthetic-key",
        "BROKER_API_SECRET": "synthetic-secret",
    }
    assert options["env"]["WRANGLER_WRITE_LOGS"] == "false"
    output = capsys.readouterr()
    assert output.out.strip() == "broker_secret_bindings_provisioned"
    assert "synthetic-key" not in output.out + output.err
    assert "synthetic-secret" not in output.out + output.err
    assert sorted(path.name for path in tmp_path.rglob("*") if path.is_file()) == [
        "wrangler",
        "wrangler.sync-runtime.template.json",
    ]


def test_noninteractive_input_fails_before_prompting(monkeypatch, capsys):
    monkeypatch.setattr(broker_secrets.sys.stdin, "isatty", lambda: False)
    prompt = Mock(side_effect=AssertionError("Prompt must not run"))
    monkeypatch.setattr(broker_secrets.getpass, "getpass", prompt)
    assert broker_secrets.main(["--confirm-read-only"]) == 2
    assert capsys.readouterr().err.strip() == "private_terminal_required"


def test_read_permission_attestation_is_required():
    with pytest.raises(SystemExit):
        broker_secrets.main([])
