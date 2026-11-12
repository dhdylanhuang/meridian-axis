"""Closed durable login-rate counters; no runtime grants or seeded buckets.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_rate_limits",
        sa.Column("bucket", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.BigInteger(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint("length(bucket) BETWEEN 1 AND 64", name="ck_login_bucket_length"),
        sa.CheckConstraint("window_started_at >= 0", name="ck_login_window_nonnegative"),
        sa.CheckConstraint("attempts BETWEEN 1 AND 1000", name="ck_login_attempts_range"),
    )
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text('ALTER TABLE "login_rate_limits" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('REVOKE ALL PRIVILEGES ON TABLE "login_rate_limits" FROM PUBLIC'))
    for role in ("anon", "authenticated"):
        if bind.scalar(
            sa.text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=:role)"), {"role": role}
        ):
            op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "login_rate_limits" FROM "{role}"'))


def downgrade():
    raise RuntimeError("Login-rate counter removal requires a reviewed forward migration")
