"""Narrow first-use credential maintenance, never a schema or grant writer.

Only generated ASCII secrets are supported. Return SQL as SecretStr so an
administrative caller must deliberately unwrap it for an in-memory stdin pipe.
"""

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

from pydantic import SecretStr

ITERATIONS = 32768


class RuntimeCredentialError(ValueError):
    pass


@dataclass(frozen=True)
class BootstrapSecret:
    password: SecretStr
    verifier: SecretStr


def scram_verifier(password: SecretStr, salt: bytes) -> SecretStr:
    if (
        not isinstance(password, SecretStr)
        or not re.fullmatch(r"[A-Za-z0-9_-]{64}", password.get_secret_value())
        or not isinstance(salt, bytes)
        or len(salt) != 16
    ):
        raise RuntimeCredentialError("runtime_credential_input_invalid")
    salted = hashlib.pbkdf2_hmac(
        "sha256", password.get_secret_value().encode("ascii"), salt, ITERATIONS
    )
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    encode = lambda value: base64.b64encode(value).decode("ascii")  # noqa: E731
    return SecretStr(
        f"SCRAM-SHA-256${ITERATIONS}:{encode(salt)}${encode(stored_key)}:{encode(server_key)}"
    )


def generate_bootstrap_secret() -> BootstrapSecret:
    password = SecretStr(secrets.token_urlsafe(48))
    return BootstrapSecret(password, scram_verifier(password, secrets.token_bytes(16)))


def _validated_verifier(verifier: SecretStr) -> str:
    if not isinstance(verifier, SecretStr):
        raise RuntimeCredentialError("runtime_verifier_invalid")
    value = verifier.get_secret_value()
    match = re.fullmatch(
        r"SCRAM-SHA-256\$32768:([A-Za-z0-9+/]{22}==)\$"
        r"([A-Za-z0-9+/]{43}=):([A-Za-z0-9+/]{43}=)",
        value,
    )
    if match is None:
        raise RuntimeCredentialError("runtime_verifier_invalid")
    for part, length in zip(match.groups(), (16, 32, 32), strict=True):
        decoded = base64.b64decode(part, validate=True)
        if len(decoded) != length or base64.b64encode(decoded).decode("ascii") != part:
            raise RuntimeCredentialError("runtime_verifier_invalid")
    return value


def credential_maintenance_sql(verifier: SecretStr, *, reset: bool = False) -> SecretStr:
    """First-use NULL→verifier, or rollback only that exact verifier to NULL.

    No arbitrary role, SQL, password or privilege option is accepted. The
    advisory lock serializes cooperating administrative attempts. The caller
    must pin the target project and keep stdout/stderr private.
    """
    value = _validated_verifier(verifier)
    if type(reset) is not bool:
        raise RuntimeCredentialError("runtime_credential_input_invalid")
    check = (
        f"current_verifier IS DISTINCT FROM '{value}'" if reset else "current_verifier IS NOT NULL"
    )
    assignment = "NULL" if reset else f"'{value}'"
    # The strict canonical verifier alphabet above excludes quotes and SQL.
    return SecretStr(f"""
DO $meridian_credential_maintenance$
DECLARE current_verifier text;
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock(87730112);
    IF current_user <> 'postgres' OR current_database() <> 'postgres'
       OR (SELECT count(*) FROM public.alembic_version) <> 1
       OR NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num='0005')
       OR NOT EXISTS (
           SELECT 1 FROM pg_catalog.pg_roles r
           WHERE rolname='meridian_bff_public' AND rolcanlogin
             AND NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit
                      OR rolreplication OR rolbypassrls)
             AND NOT pg_catalog.has_schema_privilege(r.oid,'public','CREATE')
             AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members m WHERE m.member=r.oid)
             AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class c WHERE c.relowner=r.oid)
       )
       OR EXISTS (SELECT 1 FROM public.accounts)
       OR EXISTS (SELECT 1 FROM public.account_members)
       OR EXISTS (SELECT 1 FROM public.app_sessions)
       OR EXISTS (SELECT 1 FROM public.login_rate_limits) THEN
        RAISE EXCEPTION 'Runtime credential bootstrap preconditions failed';
    END IF;
    SELECT rolpassword INTO current_verifier FROM pg_catalog.pg_authid
        WHERE rolname='meridian_bff_public';
    IF {check} THEN
        RAISE EXCEPTION 'Runtime credential state does not match this operation';
    END IF;
    ALTER ROLE meridian_bff_public PASSWORD {assignment};
END;
$meridian_credential_maintenance$;
SELECT true AS credential_operation_completed;
""")
