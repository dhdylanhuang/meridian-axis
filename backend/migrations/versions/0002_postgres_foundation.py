"""PostgreSQL hash deduplication parity and fail-closed source tables.

Revision ID: 0002
Revises: 0001

The published 0001 revision used sqlite_where only. On PostgreSQL it therefore
created an unconditional unique index, incorrectly preventing retry attempts.
Keep 0001 immutable and repair that index here. SQLite needs only the revision
advance and retains its existing schema and data.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_TABLES = ("accounts", "import_log", "source_records", "audit_log")
_API_ROLES = ("anon", "authenticated")


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("uq_import_accepted_hash", table_name="import_log")
    op.create_index(
        "uq_import_accepted_hash",
        "import_log",
        ["account_id", "kind", "content_hash"],
        unique=True,
        postgresql_where=sa.text("status = 'succeeded' AND content_hash IS NOT NULL"),
    )
    existing_api_roles = [
        role
        for role in _API_ROLES
        if bind.scalar(
            sa.text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role)"), {"role": role}
        )
    ]
    for table in _TABLES:
        # All identifiers come from this fixed reviewed allowlist. Search-path
        # ownership is the migration caller's responsibility, not user input.
        op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM PUBLIC'))
        for role in existing_api_roles:
            op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM "{role}"'))
    # No policies or Auth membership are inferred. Owners/BYPASSRLS roles retain
    # their PostgreSQL powers; least-privilege runtime access is a later gate.


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        # Restoring the old index can fail after legitimate retry records exist.
        # Restoring unknown prior grants/RLS could expose private evidence.
        raise RuntimeError("PostgreSQL hardening requires a reviewed forward migration")
