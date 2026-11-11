"""Account identity, import attempts and immutable source/audit evidence.

Revision ID: 0001
Revises: none
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("environment", sa.String(8), nullable=False),
        sa.Column("broker", sa.String(32), nullable=False),
        sa.Column("wrapper", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("private_reference", sa.Text()),
        sa.CheckConstraint("environment IN ('demo', 'live')", name="ck_account_environment"),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)", name="ck_account_currency"
        ),
    )
    op.create_table(
        "import_log",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("finished_at", sa.Text()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("counts_json", sa.Text(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("id", "account_id", name="uq_import_id_account"),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'duplicate')", name="ck_import_status"
        ),
        sa.CheckConstraint(
            "content_hash IS NULL OR length(content_hash) = 64", name="ck_import_hash_length"
        ),
    )
    op.create_index("ix_import_account_started", "import_log", ["account_id", "started_at"])
    op.create_index(
        "uq_import_accepted_hash",
        "import_log",
        ["account_id", "kind", "content_hash"],
        unique=True,
        sqlite_where=sa.text("status = 'succeeded' AND content_hash IS NOT NULL"),
    )
    op.create_table(
        "source_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("row_number", sa.Integer()),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id", "account_id"],
            ["import_log.id", "import_log.account_id"],
            name="fk_source_run_account",
        ),
        sa.UniqueConstraint("run_id", "row_number", name="uq_source_run_row"),
        sa.CheckConstraint("row_number IS NULL OR row_number > 0", name="ck_source_row_positive"),
        sa.CheckConstraint("length(digest) = 64", name="ck_source_digest_length"),
    )
    op.create_index("ix_source_account_kind", "source_records", ["account_id", "kind"])
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("occurred_at", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("import_log.id")),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_audit_occurred", "audit_log", ["occurred_at"])


def downgrade():
    op.drop_table("audit_log")
    op.drop_table("source_records")
    op.drop_table("import_log")
    op.drop_table("accounts")
