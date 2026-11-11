"""Explicit SQLite storage types that preserve precise values and UTC instants."""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


def decimal_text(value: Decimal | str | int) -> str:
    """Return a finite, context-independent, plain decimal representation.

    Decimal.normalize() can round under the active context. Formatting and
    removing insignificant fractional zeroes preserves every supplied digit.
    Floats are deliberately rejected before Decimal can capture their error.
    """
    if isinstance(value, (float, bool)) or not isinstance(value, (Decimal, str, int)):
        raise TypeError("Exact decimal values must be Decimal, string or integer")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal value") from exc
    if not number.is_finite():
        raise ValueError("Exact decimal values must be finite")
    if number.is_zero():
        return "0"
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


class ExactDecimal(TypeDecorator[Decimal]):
    """Store Decimal as TEXT, avoiding SQLite NUMERIC/REAL coercion.

    SQL SUM, casts and lexicographic ORDER BY are unsuitable for these columns.
    Read precise values and calculate/sort with Decimal in application code.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else decimal_text(value)

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(value)


class UTCDateTime(TypeDecorator[datetime]):
    """Store aware instants as fixed-format UTC text; reject naive input."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware")
        return value.astimezone(UTC).isoformat(timespec="microseconds")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None:
            raise ValueError("Stored timestamp has no timezone")
        return result.astimezone(UTC)
