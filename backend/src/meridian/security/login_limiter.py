"""Database-backed fixed-window admission before provider password verification.

One configured bucket protects a deployment, across processes and restarts.
Only a nonpersonal bucket label and counter persist. The database supplies time;
no Worker clock, request-controlled identifier or in-memory counter is trusted.
"""

import re
from collections.abc import Callable

from sqlalchemy import BigInteger, and_, case, cast, extract, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from meridian.persistence.models import LoginRateLimit


class LoginLimiterError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class DatabaseLoginLimiter:
    def __init__(
        self,
        database: Callable[[], Session],
        bucket: str,
        *,
        max_attempts: int = 5,
        window_seconds: int = 60,
    ):
        if (
            not callable(database)
            or not isinstance(bucket, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", bucket)
            or type(max_attempts) is not int
            or not 1 <= max_attempts <= 1000
            or type(window_seconds) is not int
            or not 1 <= window_seconds <= 3600
        ):
            raise LoginLimiterError("login_limiter_configuration_invalid")
        self.database, self.bucket = database, bucket
        self.max_attempts, self.window_seconds = max_attempts, window_seconds

    def _epoch(self, db: Session) -> int:
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            expression = cast(func.floor(extract("epoch", func.statement_timestamp())), BigInteger)
        elif dialect == "sqlite":
            expression = cast(func.strftime("%s", "now"), BigInteger)
        else:
            raise LoginLimiterError("login_limiter_unavailable")
        return db.scalar(select(expression))

    def consume(self) -> bool:
        """Commit one admission, or deny without sliding/incrementing the window.

        The conditional UPSERT locks/updates the single bucket atomically, rather
        than reading a counter and later writing an increment that can be lost.
        A backwards database clock fails closed until the stored window catches
        up. Calls using one bucket must share the same configured policy.
        """
        try:
            with self.database() as db, db.begin():
                dialect = db.get_bind().dialect.name
                if dialect not in {"postgresql", "sqlite"}:
                    raise LoginLimiterError("login_limiter_unavailable")
                if dialect == "postgresql":
                    # Bound row-lock/statement waits independently of an async
                    # caller timeout, which cannot interrupt synchronous DBAPI.
                    db.execute(text("SET LOCAL statement_timeout = '3s'"))
                epoch = self._epoch(db)
                if type(epoch) is not int or epoch < 0:
                    raise LoginLimiterError("login_limiter_unavailable")
                table = LoginRateLimit.__table__
                insert = postgres_insert if dialect == "postgresql" else sqlite_insert
                statement = insert(table).values(
                    bucket=self.bucket, window_started_at=epoch, attempts=1
                )
                incoming = statement.excluded.window_started_at
                reset = incoming >= table.c.window_started_at + self.window_seconds
                statement = statement.on_conflict_do_update(
                    index_elements=[table.c.bucket],
                    set_={
                        "window_started_at": case(
                            (reset, incoming), else_=table.c.window_started_at
                        ),
                        "attempts": case((reset, 1), else_=table.c.attempts + 1),
                    },
                    where=or_(
                        reset,
                        and_(
                            incoming >= table.c.window_started_at,
                            table.c.attempts < self.max_attempts,
                        ),
                    ),
                ).returning(table.c.attempts)
                permitted = db.execute(statement).scalar_one_or_none() is not None
            # Returning only after commit prevents an unrecorded admission.
            return permitted
        except Exception:
            raise LoginLimiterError("login_limiter_unavailable") from None

    async def __call__(self) -> bool:
        # The existing synchronous DBAPI/runtime path uses short transactions;
        # no transaction spans an external provider request or retry sleep.
        return self.consume()
