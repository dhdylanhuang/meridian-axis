"""Schema-scoped trusted-BFF grants; no credentials, data or identity seeds.

Revision ID: 0005
Revises: 0004
"""

from pathlib import Path

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        asset = Path(__file__).resolve().parents[1] / "sql/0005_runtime_permissions.sql"
        op.get_bind().exec_driver_sql(asset.read_text(encoding="utf-8"))


def downgrade():
    raise RuntimeError("Runtime permission removal requires a reviewed forward migration")
