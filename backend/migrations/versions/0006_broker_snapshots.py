"""Closed broker-reported snapshot read model and fixed-account runtime read.

Revision ID: 0006
Revises: 0005
"""

from pathlib import Path

import sqlalchemy as sa
from alembic import op

from meridian.persistence.types import UTCDateTime

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "broker_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("source_run_id", sa.String(64), nullable=False),
        sa.Column("observed_at", UTCDateTime(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_run_id", "account_id"],
            ["import_log.id", "import_log.account_id"],
            name="fk_snapshot_source_run_account",
        ),
        sa.UniqueConstraint("source_run_id", "account_id", name="uq_snapshot_source_account"),
        sa.CheckConstraint("length(digest) = 64", name="ck_snapshot_digest_length"),
    )
    op.create_index(
        "ix_snapshot_account_observed", "broker_snapshots", ["account_id", "observed_at"]
    )
    if op.get_bind().dialect.name == "postgresql":
        op.get_bind().exec_driver_sql(
            (Path(__file__).resolve().parents[1] / "sql/0006_snapshot_access.sql").read_text()
        )


def downgrade():
    raise RuntimeError("Snapshot removal requires a reviewed forward migration")
