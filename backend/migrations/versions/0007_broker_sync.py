"""Durable broker coordination and immutable history revisions.

Revision ID: 0007
Revises: 0006
"""

from pathlib import Path

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    root = Path(__file__).resolve().parents[1] / "sql"
    postgres = op.get_bind().dialect.name == "postgresql"
    suffix = "postgres" if postgres else "sqlite"
    for statement in (root / f"0007_sync_{suffix}.sql").read_text().split(";"):
        if statement.strip():
            op.get_bind().exec_driver_sql(statement)
    if postgres:
        op.get_bind().exec_driver_sql((root / "0007_sync_permissions.sql").read_text())


def downgrade():
    raise RuntimeError("Sync removal requires a reviewed forward migration")
