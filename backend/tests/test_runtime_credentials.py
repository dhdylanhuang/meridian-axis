"""Generated bootstrap secrets only; no real credentials or provider requests."""

import base64

import pytest
from pydantic import SecretStr
from scramp import ScramMechanism

from meridian.security.runtime_credentials import (
    ITERATIONS,
    RuntimeCredentialError,
    credential_maintenance_sql,
    generate_bootstrap_secret,
    scram_verifier,
)


def test_verifier_matches_independent_scram_implementation_and_redacts_repr():
    password, salt = SecretStr("s" * 64), b"synthetic-salt16"
    verifier = scram_verifier(password, salt)
    actual_salt, stored, server, iterations = ScramMechanism().make_auth_info(
        password.get_secret_value(), iteration_count=ITERATIONS, salt=salt
    )
    encode = lambda value: base64.b64encode(value).decode("ascii")  # noqa: E731
    assert verifier.get_secret_value() == (
        f"SCRAM-SHA-256${iterations}:{encode(actual_salt)}${encode(stored)}:{encode(server)}"
    )
    assert password.get_secret_value() not in str(verifier)
    assert verifier.get_secret_value() not in repr(verifier)


def test_generated_secrets_are_distinct_and_sql_never_contains_plaintext_password():
    first, second = generate_bootstrap_secret(), generate_bootstrap_secret()
    assert first.password != second.password and first.verifier != second.verifier
    assert len(first.password.get_secret_value()) == 64
    sql = credential_maintenance_sql(first.verifier)
    assert first.password.get_secret_value() not in sql.get_secret_value()
    assert first.password.get_secret_value() not in repr(first)
    assert first.verifier.get_secret_value() not in repr(first)
    assert first.verifier.get_secret_value() not in repr(sql)
    assert "current_verifier IS NOT NULL" in sql.get_secret_value()
    assert (
        "ALTER ROLE meridian_bff_public PASSWORD NULL"
        in credential_maintenance_sql(first.verifier, reset=True).get_secret_value()
    )


@pytest.mark.parametrize("value", [None, "unsafe", SecretStr("x' ; DROP ROLE postgres; --")])
def test_verifier_injection_or_wrong_type_is_rejected_without_echo(value):
    with pytest.raises(RuntimeCredentialError, match="runtime_verifier_invalid"):
        credential_maintenance_sql(value)


@pytest.mark.parametrize(
    "password,salt",
    [("x" * 64, b"x" * 16), (SecretStr("short"), b"x" * 16), (SecretStr("x" * 64), b"short")],
)
def test_only_generated_ascii_password_shape_and_128_bit_salt_are_supported(password, salt):
    with pytest.raises(RuntimeCredentialError, match="runtime_credential_input_invalid"):
        scram_verifier(password, salt)


def test_sync_password_maintenance_is_pinned_and_preserves_existing_data():
    from meridian.security.runtime_credentials import sync_credential_maintenance_sql

    material = generate_bootstrap_secret()
    sql = sync_credential_maintenance_sql(material.verifier).get_secret_value()
    assert "version_num='0007'" in sql
    assert "ALTER ROLE meridian_sync_public PASSWORD" in sql
    assert "current_verifier IS NOT NULL" in sql
    assert "DELETE" not in sql and "GRANT" not in sql and "CREATE ROLE" not in sql
    rollback = sync_credential_maintenance_sql(material.verifier, reset=True).get_secret_value()
    assert "current_verifier IS DISTINCT FROM" in rollback
    assert "PASSWORD NULL" in rollback
