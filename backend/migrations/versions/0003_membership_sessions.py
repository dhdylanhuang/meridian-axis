"""Closed membership and opaque-session persistence; no authorization policies.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "account_members",
        sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("auth_subject", sa.String(36), primary_key=True),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("revoked_at", sa.Text()),
        sa.CheckConstraint("slot IN (1, 2)", name="ck_member_slot"),
        sa.CheckConstraint("length(auth_subject) = 36", name="ck_member_subject_length"),
    )
    op.create_index(
        "uq_member_active_slot",
        "account_members",
        ["account_id", "slot"],
        unique=True,
        sqlite_where=sa.text("revoked_at IS NULL"),
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "app_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("auth_subject", sa.String(36), nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("revoked_at", sa.Text()),
        sa.ForeignKeyConstraint(
            ["account_id", "auth_subject"],
            ["account_members.account_id", "account_members.auth_subject"],
            name="fk_session_account_member",
        ),
        sa.CheckConstraint("length(token_hash) = 64", name="ck_session_token_hash_length"),
        sa.CheckConstraint("length(csrf_hash) = 64", name="ck_session_csrf_hash_length"),
        sa.CheckConstraint("expires_at > created_at", name="ck_session_expiry"),
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        roles = [
            role
            for role in ("anon", "authenticated")
            if bind.scalar(
                sa.text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=:role)"),
                {"role": role},
            )
        ]
        for table in ("account_members", "app_sessions"):
            op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM PUBLIC'))
            for role in roles:
                op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE "{table}" FROM "{role}"'))


def downgrade():
    raise RuntimeError("Membership/session removal requires a reviewed forward migration")
