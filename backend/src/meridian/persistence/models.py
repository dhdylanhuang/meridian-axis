"""Durable account, import and immutable evidence metadata for Stage 1A."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from meridian.persistence.types import UTCDateTime


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("environment IN ('demo', 'live')", name="ck_account_environment"),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)", name="ck_account_currency"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    environment: Mapped[str] = mapped_column(String(8), nullable=False)
    broker: Mapped[str] = mapped_column(String(32), default="trading212", nullable=False)
    wrapper: Mapped[str] = mapped_column(String(32), default="isa", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="GBP", nullable=False)
    private_reference: Mapped[str | None] = mapped_column(Text)


class AccountMember(Base):
    __tablename__ = "account_members"
    __table_args__ = (
        CheckConstraint("slot IN (1, 2)", name="ck_member_slot"),
        CheckConstraint("length(auth_subject) = 36", name="ck_member_subject_length"),
        Index(
            "uq_member_active_slot",
            "account_id",
            "slot",
            unique=True,
            sqlite_where=text("revoked_at IS NULL"),
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    auth_subject: Mapped[str] = mapped_column(String(36), primary_key=True)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class LoginRateLimit(Base):
    __tablename__ = "login_rate_limits"
    __table_args__ = (
        CheckConstraint("length(bucket) BETWEEN 1 AND 64", name="ck_login_bucket_length"),
        CheckConstraint("window_started_at >= 0", name="ck_login_window_nonnegative"),
        CheckConstraint("attempts BETWEEN 1 AND 1000", name="ck_login_attempts_range"),
    )

    bucket: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)


class AppSession(Base):
    __tablename__ = "app_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "auth_subject"],
            ["account_members.account_id", "account_members.auth_subject"],
            name="fk_session_account_member",
        ),
        CheckConstraint("length(token_hash) = 64", name="ck_session_token_hash_length"),
        CheckConstraint("length(csrf_hash) = 64", name="ck_session_csrf_hash_length"),
        CheckConstraint("expires_at > created_at", name="ck_session_expiry"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_subject: Mapped[str] = mapped_column(String(36), nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ImportRun(Base):
    __tablename__ = "import_log"
    __table_args__ = (
        UniqueConstraint("id", "account_id", name="uq_import_id_account"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'duplicate')", name="ck_import_status"
        ),
        CheckConstraint(
            "content_hash IS NULL OR length(content_hash) = 64", name="ck_import_hash_length"
        ),
        Index("ix_import_account_started", "account_id", "started_at"),
        Index(
            "uq_import_accepted_hash",
            "account_id",
            "kind",
            "content_hash",
            unique=True,
            sqlite_where=text("status = 'succeeded' AND content_hash IS NOT NULL"),
            postgresql_where=text("status = 'succeeded' AND content_hash IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_code: Mapped[str | None] = mapped_column(String(64))
    counts_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "account_id"],
            ["import_log.id", "import_log.account_id"],
            name="fk_source_run_account",
        ),
        UniqueConstraint("run_id", "row_number", name="uq_source_run_row"),
        CheckConstraint("row_number IS NULL OR row_number > 0", name="ck_source_row_positive"),
        CheckConstraint("length(digest) = 64", name="ck_source_digest_length"),
        Index("ix_source_account_kind", "account_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)


class AuditRecord(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_occurred", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("import_log.id"))
    details_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )


def _reject_mutation(_mapper, _connection, _target):
    raise ValueError("Source evidence and audit records are immutable; append a correction")


for _immutable_model in (SourceRecord, AuditRecord):
    event.listen(_immutable_model, "before_update", _reject_mutation)
    event.listen(_immutable_model, "before_delete", _reject_mutation)
