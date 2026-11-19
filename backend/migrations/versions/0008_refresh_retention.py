"""Fixed-scope bounded PostgreSQL refresh expiry, preserving daily observations."""

from pathlib import Path

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        asset = Path(__file__).resolve().parents[1] / "sql/0008_refresh_retention.sql"
        op.get_bind().exec_driver_sql(asset.read_text())


def downgrade():
    raise RuntimeError("Retention capability removal requires a reviewed forward migration")
