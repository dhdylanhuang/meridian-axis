"""Invented holdings snapshots; no source portfolio values are used."""

import csv
import io
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from meridian.adapters.holdings_csv import (
    REQUIRED_HEADERS,
    HoldingsCSVError,
    parse_holdings_csv,
)

NOW = datetime(2026, 1, 2, 12, tzinfo=UTC)
FIRST = ["SYN1", "Invented, One", "10.00", "12.50", "2.50", "0.125", "N/A", "N/A", "N/A"]
SECOND = ["SYN2", "Invented Two", "20.00", "18.25", "-1.75", "2.75", "N/A", "N/A", "N/A"]
CONTROL = ["Total", "Synthetic Group", "30.00", "30.75", "0.75", "-", "5.75", "1.25", "2.00"]


def csv_bytes(rows=None, *, headers=REQUIRED_HEADERS, bom=False):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows if rows is not None else [FIRST, SECOND, CONTROL])
    return stream.getvalue().encode("utf-8-sig" if bom else "utf-8")


def parse(content=None, **overrides):
    return parse_holdings_csv(
        csv_bytes() if content is None else content,
        **({"currency": "GBP", "observed_at": NOW} | overrides),
    )


def test_slice_identifies_ticker_total_supplies_group_and_is_not_a_holding():
    result = parse()
    assert result.group_name == "Synthetic Group"
    assert tuple(row.ticker for row in result.holdings) == ("SYN1", "SYN2")
    assert result.control.group_name != result.holdings[0].ticker
    assert result.holdings[0].owned_quantity == Decimal("0.125")
    assert result.holdings[0].name == "Invented, One"
    assert result.holdings[0].row_number == 2
    assert result.control.row_number == 4
    assert result.currency == "GBP"
    assert result.observed_at == NOW
    with pytest.raises(FrozenInstanceError):
        result.group_name = "Changed"


def test_missing_holding_dividends_are_none_and_nonadditive_controls_are_retained():
    result = parse()
    assert result.holdings[0].dividends_gained is None
    assert result.holdings[0].dividends_cash is None
    assert result.holdings[0].dividends_reinvested is None
    assert result.control.dividends_gained == Decimal("5.75")
    assert result.control.dividends_cash + result.control.dividends_reinvested != Decimal("5.75")


def test_bom_extra_columns_and_raw_csv_record_are_preserved():
    rows = [row + ["invented context"] for row in [FIRST, SECOND, CONTROL]]
    result = parse(csv_bytes(rows, headers=(*REQUIRED_HEADERS, "Extra"), bom=True))
    assert result.headers[-1] == "Extra"
    assert dict(result.holdings[0].raw_fields)["Extra"] == "invented context"
    assert result.holdings[0].raw_text.startswith('SYN1,"Invented, One",10.00')
    assert result.holdings[0].raw_text.endswith("\r\n")
    assert len(result.content_hash) == 64


def test_quoted_newline_keeps_physical_row_number_and_raw_evidence():
    row = FIRST.copy()
    row[1] = "Invented\nOne"
    result = parse(csv_bytes([row, SECOND, CONTROL]))
    assert result.holdings[0].name == "Invented\nOne"
    assert '"Invented\nOne"' in result.holdings[0].raw_text
    assert result.holdings[1].row_number == 4
    assert result.control.row_number == 5


def test_non_csv_unicode_line_separator_does_not_shift_raw_rows():
    row = FIRST.copy()
    row[1] = "Invented\u2028One"
    result = parse(csv_bytes([row, SECOND, CONTROL]))
    assert result.holdings[0].row_number == 2
    assert result.holdings[1].row_number == 3
    assert result.control.raw_text.startswith("Total,Synthetic Group,")


def test_numeric_holding_dividend_measures_are_preserved_without_becoming_payments():
    row = FIRST.copy()
    row[6:9] = ["1.0001", "0", "0.25"]
    result = parse(csv_bytes([row, SECOND, CONTROL]))
    assert result.holdings[0].dividends_gained == Decimal("1.0001")
    assert result.holdings[0].dividends_cash == Decimal(0)
    assert result.holdings[0].dividends_reinvested == Decimal("0.25")


def test_unbounded_numeric_tokens_are_rejected():
    row = FIRST.copy()
    row[2] = "1" * 257
    with pytest.raises(HoldingsCSVError, match="invalid_number"):
        parse(csv_bytes([row, SECOND, CONTROL]))


def test_precise_source_digits_and_reconciliation_ignore_global_decimal_context():
    invested = "1234567890123456789012345678901234567890.12345678901234567890"
    value = "1234567890123456789012345678901234567890.22345678901234567890"
    row = [
        "PREC",
        "Invented Precision",
        invested,
        value,
        "0.1",
        "0.00000000000000001",
        "N/A",
        "N/A",
        "N/A",
    ]
    control = ["Total", "Precision Group", invested, value, "0.1", "-", "0", "0", "0"]
    with localcontext() as context:
        context.prec = 5
        result = parse(csv_bytes([row, control]))
    assert result.holdings[0].invested_value == Decimal(invested)
    assert result.holdings[0].value == Decimal(value)
    assert result.holdings[0].result == Decimal("0.1")


def test_penny_rounding_tolerance_is_inclusive():
    control = CONTROL.copy()
    control[3] = "30.76"
    parse(csv_bytes([FIRST, SECOND, control]))


@pytest.mark.parametrize("column", ["Invested value", "Value", "Result"])
def test_control_difference_above_a_penny_rejects_whole_snapshot(column):
    control = CONTROL.copy()
    index = REQUIRED_HEADERS.index(column)
    control[index] = str(Decimal(control[index]) + Decimal("0.02"))
    with pytest.raises(HoldingsCSVError, match="mismatch"):
        parse(csv_bytes([FIRST, SECOND, control]))


@pytest.mark.parametrize("token", ["NaN", "Infinity", "1e3", "1,000.00", "£10", "", "--2", "0_1"])
def test_ambiguous_or_nonfinite_numbers_reject_without_echoing_values(token):
    row = FIRST.copy()
    row[2] = token
    with pytest.raises(HoldingsCSVError) as caught:
        parse(csv_bytes([row, SECOND, CONTROL]))
    assert caught.value.code == "invalid_number"
    assert caught.value.row_number == 2
    assert caught.value.column == "Invested value"


@pytest.mark.parametrize(
    "column,token", [("Owned quantity", "-1"), ("Value", "-2"), ("Invested value", "-2")]
)
def test_negative_quantity_or_unsigned_amount_is_invalid(column, token):
    row = FIRST.copy()
    row[REQUIRED_HEADERS.index(column)] = token
    with pytest.raises(HoldingsCSVError, match="negative_value"):
        parse(csv_bytes([row, SECOND, CONTROL]))


def test_zero_quantity_with_nonzero_value_is_invalid():
    row = FIRST.copy()
    row[5] = "0"
    with pytest.raises(HoldingsCSVError, match="value_without_quantity"):
        parse(csv_bytes([row, SECOND, CONTROL]))


def test_closed_zero_holding_is_preserved_without_fabricating_a_position():
    row = ["CLOSED", "Invented Closed", "0", "0", "0", "0", "N/A", "N/A", "N/A"]
    result = parse(csv_bytes([FIRST, SECOND, row, CONTROL]))
    assert result.holdings[-1].owned_quantity == Decimal(0)


@pytest.mark.parametrize("rows", [[FIRST], [CONTROL], [CONTROL, FIRST], [FIRST, CONTROL, CONTROL]])
def test_missing_misplaced_or_multiple_total_controls_are_invalid(rows):
    with pytest.raises(HoldingsCSVError):
        parse(csv_bytes(rows))


@pytest.mark.parametrize("column", ["Name", "Slice"])
def test_missing_holding_identity_rejects_entire_file(column):
    row = FIRST.copy()
    row[REQUIRED_HEADERS.index(column)] = " "
    with pytest.raises(HoldingsCSVError, match="missing_holding_identity"):
        parse(csv_bytes([row, SECOND, CONTROL]))


@pytest.mark.parametrize(
    "field,value,code", [(1, "", "missing_group_name"), (5, "0", "invalid_control_quantity")]
)
def test_group_context_and_control_quantity_are_required(field, value, code):
    control = CONTROL.copy()
    control[field] = value
    with pytest.raises(HoldingsCSVError, match=code):
        parse(csv_bytes([FIRST, SECOND, control]))


def test_line_result_arithmetic_is_checked_before_acceptance():
    row = FIRST.copy()
    row[4] = "999"
    with pytest.raises(HoldingsCSVError, match="result_mismatch"):
        parse(csv_bytes([row, SECOND, CONTROL]))


def test_duplicate_headers_or_missing_required_headers_are_invalid():
    with pytest.raises(HoldingsCSVError, match="invalid_headers"):
        parse(csv_bytes(headers=(*REQUIRED_HEADERS[:-1], "Name")))
    with pytest.raises(HoldingsCSVError, match="missing_headers"):
        parse(csv_bytes(headers=(*REQUIRED_HEADERS[:-1], "Unrecognised")))


def test_empty_bad_encoding_malformed_and_wrong_width_are_invalid():
    for content, code in [
        (b"", "empty_file"),
        (b"\xff", "invalid_encoding"),
        (csv_bytes([FIRST[:-1], CONTROL]), "invalid_column_count"),
        (csv_bytes() + b"\r\n", "invalid_column_count"),
        (csv_bytes().split(b"\r\n", 1)[0] + b'\r\n"unterminated', "malformed_csv"),
    ]:
        with pytest.raises(HoldingsCSVError, match=code):
            parse(content)


def test_size_and_row_limits_are_checked():
    with pytest.raises(HoldingsCSVError, match="file_too_large"):
        parse(max_bytes=1)
    with pytest.raises(HoldingsCSVError, match="too_many_rows"):
        parse(max_rows=2)


def test_external_currency_and_aware_observation_time_are_mandatory():
    with pytest.raises(HoldingsCSVError, match="invalid_currency"):
        parse(currency="gbp")
    with pytest.raises(HoldingsCSVError, match="observation_time_required"):
        parse(observed_at=datetime(2026, 1, 2))
    supplied = NOW.astimezone(timezone(timedelta(hours=8)))
    assert parse(observed_at=supplied).observed_at.tzinfo is UTC


def test_raw_extra_field_cannot_hide_a_nul_character():
    rows = [FIRST + ["hidden\x00value"], SECOND + [""], CONTROL + [""]]
    with pytest.raises(HoldingsCSVError, match="invalid_character"):
        parse(csv_bytes(rows, headers=(*REQUIRED_HEADERS, "Extra")))
