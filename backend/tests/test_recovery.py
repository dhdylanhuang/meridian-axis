import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from meridian import hosted_backup, local_restore, recovery

FILES = {name: b"-- synthetic SQL\n" for name in recovery.FILES}


def test_authenticated_roundtrip_and_private_exclusive_key(tmp_path):
    key_path = tmp_path / "key"
    recovery.create_key(key_path)
    key = recovery.read_key(key_path)
    controls = {"revision": "0005", "synthetic_decimal": "0.123456789012345678901"}
    first = recovery.seal(FILES, controls, key)
    second = recovery.seal(FILES, controls, key)
    assert first != second
    assert b"synthetic_decimal" not in first
    assert recovery.unseal(first, key) == (FILES, controls)
    with pytest.raises(FileExistsError):
        recovery.create_key(key_path)
    assert recovery.read_key(key_path) == key


@pytest.mark.parametrize("change", ["ciphertext", "nonce", "wrong_key", "truncated", "header"])
def test_corruption_and_wrong_key_are_rejected(change):
    key = AESGCM.generate_key(bit_length=256)
    archive = bytearray(recovery.seal(FILES, {}, key))
    if change == "wrong_key":
        key = AESGCM.generate_key(bit_length=256)
    elif change == "truncated":
        archive = archive[:-1]
    else:
        position = {"ciphertext": -1, "nonce": len(recovery.MAGIC), "header": 0}[change]
        archive[position] ^= 1
    with pytest.raises(recovery.RecoveryError):
        recovery.unseal(bytes(archive), key)


def test_invalid_key_and_symlink_rejected(tmp_path):
    key = tmp_path / "key"
    recovery.private_write(key, b"invalid")
    with pytest.raises(recovery.RecoveryError):
        recovery.read_key(key)
    link = tmp_path / "link"
    try:
        link.symlink_to(key)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(recovery.RecoveryError):
        recovery.read_key(link)


def test_unsafe_source_or_mutating_source_never_creates_archive(tmp_path, monkeypatch):
    key = tmp_path / "key"
    recovery.create_key(key)
    destination = tmp_path / "archive"
    monkeypatch.setattr(hosted_backup, "controls", Mock(side_effect=[{"x": 1}, {"x": 2}]))
    monkeypatch.setattr(hosted_backup, "run", Mock(return_value=b"-- synthetic SQL"))
    with pytest.raises(recovery.RecoveryError, match="source_changed"):
        hosted_backup.backup(Path("cli"), "a" * 20, destination, key)
    assert not destination.exists()
    with pytest.raises(recovery.RecoveryError, match="project_invalid"):
        hosted_backup.backup(Path("cli"), "--malicious", destination, key)


def test_successful_export_verifies_persisted_archive(tmp_path, monkeypatch):
    key = tmp_path / "key"
    recovery.create_key(key)
    destination = tmp_path / "archive"
    monkeypatch.setattr(hosted_backup, "controls", Mock(return_value={"revision": "0005"}))
    monkeypatch.setattr(hosted_backup, "run", Mock(return_value=b"-- synthetic SQL"))
    result = hosted_backup.backup(Path("cli"), "a" * 20, destination, key)
    assert result["status"] == "backup_verified"
    assert result["restore_verified"] is False
    files, controls = recovery.load_archive(destination, key)
    assert set(files) == recovery.FILES
    assert controls["database"] == {"revision": "0005"}


def test_export_refuses_role_passwords(tmp_path, monkeypatch):
    key = tmp_path / "key"
    recovery.create_key(key)
    monkeypatch.setattr(hosted_backup, "controls", Mock(return_value={}))
    monkeypatch.setattr(hosted_backup, "run", Mock(return_value=b"PASSWORD 'synthetic'"))
    with pytest.raises(recovery.RecoveryError, match="role_password"):
        hosted_backup.backup(Path("cli"), "a" * 20, tmp_path / "archive", key)
    assert not (tmp_path / "archive").exists()


@pytest.mark.parametrize(
    "networks,project,running",
    [({"lan": {}}, "recovery-test", True), ({}, "other", True), ({}, "recovery-test", False)],
)
def test_restore_refuses_network_or_ownership_mismatch(monkeypatch, networks, project, running):
    monkeypatch.setattr(
        local_restore,
        "run",
        lambda _: json.dumps(
            [
                {
                    "Config": {"Labels": {"com.supabase.cli.project": project}},
                    "NetworkSettings": {"Networks": networks},
                    "State": {"Running": running},
                }
            ]
        ).encode(),
    )
    with pytest.raises(recovery.RecoveryError, match="isolation_unverified"):
        local_restore.target("supabase_db_recovery-test")


def test_restore_refuses_production_name_without_running_command(monkeypatch):
    run = Mock()
    monkeypatch.setattr(local_restore, "run", run)
    with pytest.raises(recovery.RecoveryError, match="name_invalid"):
        local_restore.target("supabase_db_production")
    run.assert_not_called()


def test_failed_command_never_displays_captured_secrets(monkeypatch):
    monkeypatch.setattr(hosted_backup.subprocess, "run", Mock(side_effect=RuntimeError("secret")))
    with pytest.raises(recovery.RecoveryError) as error:
        hosted_backup.run(["synthetic"])
    assert str(error.value) == "recovery_command_failed"


def test_restore_is_atomic_checks_controls_then_revokes_sessions(tmp_path, monkeypatch):
    key = tmp_path / "key"
    recovery.create_key(key)
    archive = tmp_path / "archive"
    files = {
        "roles.sql": b"-- synthetic roles\n",
        "schema.sql": b"-- synthetic schema\n",
        "data.sql": b"COPY public.accounts (id) FROM stdin;\nsynthetic\n\\.\n",
    }
    recovery.private_write(
        archive, recovery.seal(files, {"database": {"revision": "0005"}}, recovery.read_key(key))
    )
    monkeypatch.setattr(local_restore, "target", Mock())
    execute = Mock(side_effect=[b"0\n", b""])
    monkeypatch.setattr(local_restore, "psql", execute)
    result = local_restore.restore("supabase_db_recovery-test", archive, key)
    script = execute.call_args_list[-1].args[1]
    assert script.startswith(b"BEGIN;")
    assert script.endswith(b"COMMIT;\n")
    assert script.index(b"restore_controls_mismatch") < script.index(b"UPDATE public.app_sessions")
    assert b"AT TIME ZONE 'UTC'" in script
    assert b"DELETE FROM auth.refresh_tokens; DELETE FROM auth.sessions;" in script
    assert result["hosted_auth_recovery_verified"] is False


def test_restore_nonempty_target_never_runs_sql_payload(tmp_path, monkeypatch):
    key = tmp_path / "key"
    recovery.create_key(key)
    archive = tmp_path / "archive"
    recovery.private_write(archive, recovery.seal(FILES, {"database": {}}, recovery.read_key(key)))
    monkeypatch.setattr(local_restore, "target", Mock())
    execute = Mock(return_value=b"1\n")
    monkeypatch.setattr(local_restore, "psql", execute)
    with pytest.raises(recovery.RecoveryError, match="target_not_empty"):
        local_restore.restore("supabase_db_recovery-test", archive, key)
    assert execute.call_count == 1


@pytest.mark.parametrize("failure", ["storage", "revision", "unknown_table"])
def test_backup_controls_fail_closed_on_unsupported_scope(monkeypatch, failure):
    expected = sorted(t.split(".")[1] for t in hosted_backup.TABLES if t.startswith("public."))
    data = {
        "revision": "0005",
        "public_tables": expected,
        "storage.buckets": {"count": 0},
        "storage.objects": {"count": 0},
    }
    if failure == "storage":
        data["storage.objects"]["count"] = 1
    elif failure == "revision":
        data["revision"] = "9999"
    else:
        data["public_tables"].append("unexpected_new_table")
    monkeypatch.setattr(
        hosted_backup, "run", Mock(return_value=json.dumps({"rows": [{"controls": data}]}).encode())
    )
    with pytest.raises(recovery.RecoveryError):
        hosted_backup.controls(Path("cli"), "a" * 20)


def test_native_migration_history_is_exported_explicitly(tmp_path, monkeypatch):
    key = tmp_path / "key"
    recovery.create_key(key)
    monkeypatch.setattr(hosted_backup, "controls", Mock(return_value={}))
    execute = Mock(return_value=b"-- synthetic SQL")
    monkeypatch.setattr(hosted_backup, "run", execute)
    hosted_backup.backup(Path("cli"), "a" * 20, tmp_path / "archive", key)
    calls = [call.args[0] for call in execute.call_args_list]
    assert any(
        "--data-only" in args and "--schema" in args and args[-1] == "supabase_migrations"
        for args in calls
    )
    assert any("--schema" in args and args[-1] == "public,supabase_migrations" for args in calls)
