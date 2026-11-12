"""Run with python -m meridian.hosted_backup. Uses an already authenticated CLI.

No plaintext dump is written to disk. A stable source is required across separate
provider exports: before/after content controls fail closed on concurrent writes.
This bounded first implementation refuses nonempty Storage or unknown app tables.
"""

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

from meridian.recovery import RecoveryError, create_key, load_archive, private_write, read_key, seal

TABLES = (
    "public.accounts",
    "public.account_members",
    "public.app_sessions",
    "public.audit_log",
    "public.import_log",
    "public.source_records",
    "public.login_rate_limits",
    "public.alembic_version",
    "auth.users",
    "auth.identities",
    "storage.buckets",
    "storage.objects",
    "supabase_migrations.schema_migrations",
)
# Content hashes remain inside the encrypted archive. No real identifiers/amounts
# are ever printed. C ordering makes source/restore comparison locale independent.
CONTROLS_SQL = (
    "SELECT jsonb_build_object("
    + ",".join(
        "'" + table + "', (SELECT jsonb_build_object('count', count(*), 'digest', "
        "md5(COALESCE(string_agg(row_to_json(t)::text, E'\\n' "
        "ORDER BY row_to_json(t)::text COLLATE \"C\"), ''))) FROM " + table + " t)"
        for table in TABLES
    )
    + ", 'revision', (SELECT version_num FROM public.alembic_version), "
    + (
        "'public_tables', (SELECT jsonb_agg(tablename ORDER BY tablename) FROM pg_tables "
        "WHERE schemaname='public')) AS controls;"
    )
)


def run(args: list[str], *, data: bytes | None = None, timeout: int = 300) -> bytes:
    try:
        result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
        if result.returncode:
            raise ValueError
        return result.stdout
    except Exception:
        raise RecoveryError("recovery_command_failed") from None


def controls(cli: Path, project: str) -> dict:
    output = run(
        [
            str(cli),
            "db",
            "query",
            f"--remote={project}",
            "--file",
            "/dev/stdin",
            "--read-only",
            "--output-format",
            "json",
            "--log-level",
            "none",
        ],
        data=CONTROLS_SQL.encode(),
        timeout=60,
    )
    try:
        result = json.loads(output)["rows"][0]["controls"]
        expected = sorted(t.split(".")[1] for t in TABLES if t.startswith("public."))
        if result["revision"] != "0005" or result["public_tables"] != expected:
            raise ValueError
        if any(result[t]["count"] for t in ("storage.buckets", "storage.objects")):
            raise RecoveryError("recovery_storage_objects_unsupported")
        return result
    except RecoveryError:
        raise
    except Exception:
        raise RecoveryError("recovery_controls_invalid") from None


def backup(cli: Path, project: str, destination: Path, key_path: Path) -> dict:
    if not re.fullmatch(r"[a-z]{20}", project):
        raise RecoveryError("recovery_project_invalid")
    if destination.exists():
        raise RecoveryError("recovery_destination_exists")
    key = read_key(key_path)
    started = time.monotonic()
    before = controls(cli, project)
    files = {}
    for name, flags in (
        ("roles.sql", ["--role-only"]),
        ("schema.sql", ["--schema", "public,supabase_migrations"]),
        ("data.sql", ["--data-only", "--use-copy"]),
    ):
        files[name] = run(
            [
                str(cli),
                "db",
                "dump",
                f"--remote={project}",
                "--log-level",
                "none",
                *flags,
            ]
        )
    # The CLI intentionally excludes its own migration history from the default
    # data export. Export that schema explicitly so native delivery parity is
    # recoverable alongside the application parity marker.
    files["data.sql"] += b"\n" + run(
        [
            str(cli),
            "db",
            "dump",
            f"--remote={project}",
            "--log-level",
            "none",
            "--data-only",
            "--use-copy",
            "--schema",
            "supabase_migrations",
        ]
    )
    if controls(cli, project) != before:
        raise RecoveryError("recovery_source_changed_retry_when_quiet")
    # CLI role dumps must omit reusable password verifiers.
    if any(value in files["roles.sql"] for value in (b"SCRAM-SHA-256$", b"PASSWORD '")):
        raise RecoveryError("recovery_role_password_present")
    private_write(destination, seal(files, {"project": project, "database": before}, key))
    load_archive(destination, key_path)
    return {
        "status": "backup_verified",
        "encrypted_bytes": destination.stat().st_size,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "storage_objects": 0,
        "restore_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    key = sub.add_parser("new-key")
    key.add_argument("path", type=Path)
    export = sub.add_parser("backup")
    export.add_argument("--cli", type=Path, required=True)
    export.add_argument("--project", required=True)
    export.add_argument("--key-file", type=Path, required=True)
    export.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "new-key":
            create_key(args.path)
            result = {"status": "key_created"}
        else:
            result = backup(args.cli.resolve(), args.project, args.destination, args.key_file)
        print(json.dumps(result))
    except Exception as error:
        code = str(error) if isinstance(error, RecoveryError) else "recovery_operation_failed"
        print(json.dumps({"status": "failed", "category": code}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
