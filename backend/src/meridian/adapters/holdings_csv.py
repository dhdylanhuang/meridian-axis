"""Pure parser for the verified group-holdings snapshot, never a trade importer.

All fixtures are synthetic. Currency and observation time are supplied by the
caller because neither is present in this export. Slice identifies a ticker;
only the final Total row supplies the group label. Raw evidence is retained.
"""

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, localcontext

REQUIRED_HEADERS = (
    "Slice",
    "Name",
    "Invested value",
    "Value",
    "Result",
    "Owned quantity",
    "Dividends gained",
    "Dividends cash",
    "Dividends reinvested",
)
SCHEMA_VERSION = "trading212/holdings-snapshot/v1"
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_ROWS = 10_000
MAX_NUMBER_LENGTH = 256
PENNY = Decimal("0.01")
_PLAIN_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")
_CURRENCY = re.compile(r"[A-Z]{3}\Z")


class HoldingsCSVError(ValueError):
    """A safe diagnostic that deliberately omits supplied financial values."""

    def __init__(self, code: str, *, row_number: int | None = None, column: str | None = None):
        self.code = code
        self.row_number = row_number
        self.column = column
        location = f" at row {row_number}" if row_number is not None else ""
        location += f" ({column})" if column else ""
        super().__init__(f"{code}{location}")


@dataclass(frozen=True)
class HoldingSnapshotRow:
    row_number: int
    ticker: str
    name: str
    invested_value: Decimal
    value: Decimal
    result: Decimal
    owned_quantity: Decimal
    dividends_gained: Decimal | None
    dividends_cash: Decimal | None
    dividends_reinvested: Decimal | None
    raw_fields: tuple[tuple[str, str], ...]
    raw_text: str


@dataclass(frozen=True)
class SnapshotControl:
    row_number: int
    group_name: str
    invested_value: Decimal
    value: Decimal
    result: Decimal
    dividends_gained: Decimal
    dividends_cash: Decimal
    dividends_reinvested: Decimal
    raw_fields: tuple[tuple[str, str], ...]
    raw_text: str


@dataclass(frozen=True)
class HoldingSnapshot:
    currency: str
    observed_at: datetime
    group_name: str
    holdings: tuple[HoldingSnapshotRow, ...]
    control: SnapshotControl
    headers: tuple[str, ...]
    content_hash: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class _RawRow:
    row_number: int
    fields: tuple[tuple[str, str], ...]
    text: str

    def mapping(self) -> dict[str, str]:
        return dict(self.fields)


def _number(value: str, row: int, column: str, *, nonnegative=False) -> Decimal:
    token = value.strip()
    if len(token) > MAX_NUMBER_LENGTH or not _PLAIN_NUMBER.fullmatch(token):
        raise HoldingsCSVError("invalid_number", row_number=row, column=column)
    result = Decimal(token)
    if nonnegative and result < 0:
        raise HoldingsCSVError("negative_value", row_number=row, column=column)
    return result


def _dividend(value: str, row: int, column: str, *, required: bool) -> Decimal | None:
    if not required and value.strip() == "N/A":
        return None
    return _number(value, row, column, nonnegative=True)


def _read_rows(text: str, max_rows: int) -> tuple[tuple[str, ...], list[_RawRow]]:
    # splitlines() also splits Unicode paragraph separators and vertical tabs;
    # csv.reader counts only physical CR/LF lines. Keep those views identical.
    physical_lines = io.StringIO(text, newline="").readlines()
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        headers = tuple(next(reader))
        if (
            not headers
            or any(not header or "\x00" in header or header != header.strip() for header in headers)
            or len(set(headers)) != len(headers)
        ):
            raise HoldingsCSVError("invalid_headers", row_number=1)
        if not set(REQUIRED_HEADERS).issubset(headers):
            raise HoldingsCSVError("missing_headers", row_number=1)
        rows = []
        prior_line = reader.line_num
        for fields in reader:
            row_number = prior_line + 1
            raw_text = "".join(physical_lines[prior_line : reader.line_num])
            prior_line = reader.line_num
            if len(rows) >= max_rows:
                raise HoldingsCSVError("too_many_rows", row_number=row_number)
            if len(fields) != len(headers):
                raise HoldingsCSVError("invalid_column_count", row_number=row_number)
            if any("\x00" in field for field in fields):
                raise HoldingsCSVError("invalid_character", row_number=row_number)
            rows.append(_RawRow(row_number, tuple(zip(headers, fields, strict=True)), raw_text))
        return headers, rows
    except StopIteration as exc:
        raise HoldingsCSVError("empty_file") from exc
    except csv.Error as exc:
        raise HoldingsCSVError("malformed_csv", row_number=reader.line_num) from exc


def _holding(raw: _RawRow) -> HoldingSnapshotRow:
    fields = raw.mapping()
    row = raw.row_number
    ticker, name = fields["Slice"].strip(), fields["Name"].strip()
    if not ticker or not name:
        raise HoldingsCSVError("missing_holding_identity", row_number=row)
    value = _number(fields["Value"], row, "Value", nonnegative=True)
    quantity = _number(fields["Owned quantity"], row, "Owned quantity", nonnegative=True)
    if quantity == 0 and value != 0:
        raise HoldingsCSVError("value_without_quantity", row_number=row)
    return HoldingSnapshotRow(
        row_number=row,
        ticker=ticker,
        name=name,
        invested_value=_number(fields["Invested value"], row, "Invested value", nonnegative=True),
        value=value,
        result=_number(fields["Result"], row, "Result"),
        owned_quantity=quantity,
        dividends_gained=_dividend(
            fields["Dividends gained"], row, "Dividends gained", required=False
        ),
        dividends_cash=_dividend(fields["Dividends cash"], row, "Dividends cash", required=False),
        dividends_reinvested=_dividend(
            fields["Dividends reinvested"], row, "Dividends reinvested", required=False
        ),
        raw_fields=raw.fields,
        raw_text=raw.text,
    )


def _control(raw: _RawRow) -> SnapshotControl:
    fields = raw.mapping()
    row = raw.row_number
    name = fields["Name"].strip()
    if not name:
        raise HoldingsCSVError("missing_group_name", row_number=row)
    if fields["Owned quantity"].strip() != "-":
        raise HoldingsCSVError("invalid_control_quantity", row_number=row, column="Owned quantity")
    return SnapshotControl(
        row_number=row,
        group_name=name,
        invested_value=_number(fields["Invested value"], row, "Invested value", nonnegative=True),
        value=_number(fields["Value"], row, "Value", nonnegative=True),
        result=_number(fields["Result"], row, "Result"),
        dividends_gained=_number(
            fields["Dividends gained"], row, "Dividends gained", nonnegative=True
        ),
        dividends_cash=_number(fields["Dividends cash"], row, "Dividends cash", nonnegative=True),
        dividends_reinvested=_number(
            fields["Dividends reinvested"], row, "Dividends reinvested", nonnegative=True
        ),
        raw_fields=raw.fields,
        raw_text=raw.text,
    )


def _reconcile(holdings: tuple[HoldingSnapshotRow, ...], control: SnapshotControl) -> None:
    monetary = [
        amount
        for row in (*holdings, control)
        for amount in (row.invested_value, row.value, row.result)
    ]
    # Decimal construction is exact; arithmetic still needs an adequate local
    # context. Size it for every supplied integer/fractional digit plus carry.
    max_integer = max(max(0, value.adjusted() + 1) for value in monetary)
    max_fraction = max(max(0, -value.as_tuple().exponent) for value in monetary)
    with localcontext() as context:
        context.prec = max(50, max_integer + max_fraction + len(str(len(holdings))) + 3)
        for row in (*holdings, control):
            if abs(row.value - row.invested_value - row.result) > PENNY:
                raise HoldingsCSVError(
                    "result_mismatch", row_number=row.row_number, column="Result"
                )
        for attribute in ("invested_value", "value", "result"):
            total = sum((getattr(row, attribute) for row in holdings), Decimal(0))
            if abs(total - getattr(control, attribute)) > PENNY:
                raise HoldingsCSVError("control_mismatch", row_number=control.row_number)
    # Dividend controls are deliberately not added or forced to reconcile:
    # their labels have not been established as additive income components.


def parse_holdings_csv(
    content: bytes,
    *,
    currency: str,
    observed_at: datetime,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> HoldingSnapshot:
    """Parse and reconcile the complete snapshot or raise a safe diagnostic.

    ``max_rows`` counts data records, including the final Total control. Numeric
    fields accept ordinary decimal strings only (maximum 256 characters), not
    scientific notation, currency symbols or locale-specific separators.
    Compatible extra columns are preserved without assigning them semantics.
    No listing mapping, transaction, dividend payment or group override occurs.
    """
    if not isinstance(currency, str) or not _CURRENCY.fullmatch(currency):
        raise HoldingsCSVError("invalid_currency")
    if not isinstance(observed_at, datetime) or observed_at.utcoffset() is None:
        raise HoldingsCSVError("observation_time_required")
    if max_bytes <= 0 or max_rows < 2:
        raise ValueError("Snapshot limits must permit a holding and control")
    if not isinstance(content, bytes):
        raise TypeError("Snapshot content must be bytes")
    if len(content) > max_bytes:
        raise HoldingsCSVError("file_too_large")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HoldingsCSVError("invalid_encoding") from exc
    headers, raw_rows = _read_rows(text, max_rows)
    controls = [index for index, row in enumerate(raw_rows) if row.mapping()["Slice"] == "Total"]
    if len(controls) != 1 or controls[0] != len(raw_rows) - 1:
        raise HoldingsCSVError("invalid_total_control")
    if len(raw_rows) < 2:
        raise HoldingsCSVError("no_holdings")
    holdings = tuple(_holding(row) for row in raw_rows[:-1])
    control = _control(raw_rows[-1])
    _reconcile(holdings, control)
    return HoldingSnapshot(
        currency=currency,
        observed_at=observed_at.astimezone(UTC),
        group_name=control.group_name,
        holdings=holdings,
        control=control,
        headers=headers,
        content_hash=hashlib.sha256(content).hexdigest(),
    )
