"""Restore only into a network-disconnected, labelled local Supabase container.

There is intentionally no URL or hosted-target parameter. Uses the documented
Supabase roles/schema/data SQL sequence; the target must be disposable and empty.
"""

import argparse
import json
import re
import time
from pathlib import Path

from meridian.hosted_backup import CONTROLS_SQL, run
from meridian.recovery import RecoveryError, load_archive


def target(container: str) -> None:
    if not re.fullmatch(r"supabase_db_(?:meridian-)?recovery-[a-z0-9-]+", container):
        raise RecoveryError("restore_target_name_invalid")
    try:
        info = json.loads(run(["docker", "inspect", container]))[0]
        project = container.removeprefix("supabase_db_")
        if info["Config"]["Labels"]["com.supabase.cli.project"] != project:
            raise ValueError
        if info["NetworkSettings"]["Networks"]:
            raise ValueError
        if not info["State"]["Running"]:
            raise ValueError
    except Exception:
        raise RecoveryError("restore_target_isolation_unverified") from None


def psql(container: str, sql: bytes) -> bytes:
    return run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-X",
            "-q",
            "-A",
            "-t",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "supabase_admin",
            "-d",
            "postgres",
        ],
        data=sql,
    )


def restore(container: str, archive: Path, key_file: Path) -> dict:
    target(container)
    files, manifest = load_archive(archive, key_file)
    if (
        psql(
            container,
            b"SELECT (SELECT count(*) FROM pg_tables WHERE schemaname='public') "
            b"+ (SELECT count(*) FROM auth.users) + (SELECT count(*) FROM storage.objects);",
        ).strip()
        != b"0"
    ):
        raise RecoveryError("restore_target_not_empty")
    expected = manifest["database"]
    # SQL is accepted only from the authenticated administrator archive. No table
    # identifier or path is supplied by a web request. Clear only dump-listed
    # provider baseline rows (e.g. auth schema migration versions) on this target.
    tables = re.findall(
        rb'^COPY ((?:"?[a-zA-Z_][a-zA-Z0-9_]*"?\.)"?[a-zA-Z_][a-zA-Z0-9_]*"?) \(',
        files["data.sql"],
        re.MULTILINE,
    )
    if not tables:
        raise RecoveryError("restore_copy_tables_missing")
    expected_sql = json.dumps(expected, sort_keys=True).replace("'", "''")
    controls_select = CONTROLS_SQL.removesuffix(";")
    verify = (
        "DO $meridian_verify$ DECLARE actual jsonb; BEGIN SELECT controls INTO actual FROM ("
        + controls_select
        + ") AS snapshot; IF actual IS DISTINCT FROM '"
        + expected_sql
        + "'::jsonb THEN RAISE EXCEPTION 'restore_controls_mismatch'; END IF; "
        "END $meridian_verify$;"
    ).encode()
    script = b"BEGIN;\n" + files["roles.sql"] + b"\n" + files["schema.sql"]
    script += b"\nSET session_replication_role = replica;\nTRUNCATE "
    script += b", ".join(sorted(set(tables))) + b" CASCADE;\n" + files["data.sql"]
    script += b"\n" + verify + b"\n"
    # A recovered database must never resurrect browser/provider sessions. Exact
    # source controls are checked first, then session invalidation is deliberate.
    script += (
        b"UPDATE public.app_sessions SET revoked_at=COALESCE(revoked_at, "
        b"to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', "
        b"""'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'));\n"""
        b"DELETE FROM auth.refresh_tokens; DELETE FROM auth.sessions;\n"
        b"SET session_replication_role = origin;\nCOMMIT;\n"
    )
    started = time.monotonic()
    psql(container, script)
    return {
        "status": "restore_verified",
        "content_controls_match": True,
        "sessions_invalidated": True,
        "target_network_disconnected": True,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "hosted_auth_recovery_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(restore(args.container, args.archive, args.key_file)))
    except Exception as error:
        code = str(error) if isinstance(error, RecoveryError) else "restore_operation_failed"
        print(json.dumps({"status": "failed", "category": code}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
