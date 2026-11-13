"""Synthetic Excel XML fixtures exercise provenance, decimal controls and rollback."""

import io
import json
import zipfile
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from meridian.adapters.workbook_baseline import (
    GroupCells,
    ObservationCells,
    WorkbookBaselineError,
    WorkbookBaselineLayout,
    parse_workbook_baseline,
)
from meridian.application import workbook_import
from meridian.application.workbook_import import import_workbook_baseline
from meridian.persistence.database import create_db_engine, upgrade_database
from meridian.persistence.models import Account, AuditRecord, ImportRun, SourceRecord

NOW = datetime(2026, 1, 2, tzinfo=UTC)


def layout():
    return WorkbookBaselineLayout(
        "Monthly Tracking",
        tuple(
            ObservationCells(
                label=f"A{row}",
                value=f"B{row}",
                invested=f"C{row}",
                groups=(
                    GroupCells("Alpha", f"D{row}", f"E{row}"),
                    GroupCells(
                        "Beta", None if row == 5 else f"F{row}", None if row == 5 else f"G{row}"
                    ),
                ),
                observed_on=None if row == 6 else date(2026, 1, row),
                date_precision="unknown" if row == 6 else "day",
                notes=f"H{row}",
                cumulative_dividends=f"I{row}",
            )
            for row in range(5, 11)
        ),
    )


def workbook(*, change=None):
    cells = {}
    for row in range(5, 11):
        cells |= {
            f"A{row}": f'<c r="A{row}" t="inlineStr"><is><t>Observation {row}</t></is></c>',
            f"B{row}": f'<c r="B{row}"><f>SUM(D{row},F{row})</f><v>'
            + ("100.1234567890123456789" if row == 5 else "300.1234567890123456789")
            + "</v></c>",
            f"C{row}": f'<c r="C{row}"><v>{"90" if row == 5 else "270"}</v></c>',
            f"D{row}": f'<c r="D{row}"><v>100.1234567890123456789</v></c>',
            f"E{row}": f'<c r="E{row}"><v>90</v></c>',
            f"F{row}": f'<c r="F{row}"><v>200</v></c>',
            f"G{row}": f'<c r="G{row}"><v>180</v></c>',
            f"H{row}": f'<c r="H{row}" t="inlineStr"><is><t>'
            + escape("Private synthetic note & context")
            + "</t></is></c>",
            f"I{row}": f'<c r="I{row}"><v>0</v></c>',
        }
    if change:
        cells.update(change)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<workbook
            xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
            <sheets><sheet name="Monthly Tracking" sheetId="1" r:id="rId1"/></sheets>
            </workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<Relationships
            xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
            <Relationship Id="rId1" Target="worksheets/sheet1.xml"
            Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>
            </Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<worksheet
            xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>"""
            + "<row>"
            + "".join(cells.values())
            + "</row></sheetData></worksheet>",
        )
    return stream.getvalue()


def test_preserves_all_six_exact_values_unknown_date_missing_group_and_formula_cache():
    result = parse_workbook_baseline(workbook(), layout=layout())
    assert len(result.observations) == 6
    first, july = result.observations[:2]
    assert first["value"] == "100.1234567890123456789"
    assert first["recorded_invested"] == "90"
    assert first["invested_basis"] == "recorded_holding_cost"
    assert first["raw_cells"]["B5"]["formula"] == "SUM(D5,F5)"
    assert first["missing_groups"] == ["Beta"]
    assert first["groups"][1]["value"] is None
    assert first["coverage"] == "incomplete"
    assert july["observed_on"] is None
    assert july["date_precision"] == "unknown"
    assert july["notes"] == "Private synthetic note & context"
    assert july["cumulative_dividends"] == "0"
    assert july["dividend_basis"] == "cumulative_observation_coverage_unknown"
    assert all(row["provenance"] == "excel_migration" for row in result.observations)
    assert all(row["invested_reconciled"] for row in result.observations)


@pytest.mark.parametrize(
    "cell,xml,code",
    [
        ("B6", '<c r="B6"><v>301</v></c>', "baseline_value_mismatch"),
        ("C6", '<c r="C6"><v>271</v></c>', "baseline_invested_mismatch"),
        ("B6", '<c r="B6"><f>SUM(D6,F6)</f><v/></c>', "numeric_cell_or_cache_required"),
        ("D6", '<c r="D6" t="e"><v>#REF!</v></c>', "numeric_cell_or_cache_required"),
        ("D6", '<c r="D6"><v>-1</v></c>', "invalid_baseline_amount"),
        ("D6", '<c r="D6"><v>1e99999999</v></c>', "invalid_baseline_amount"),
    ],
)
def test_invalid_economics_or_missing_cache_rejects_whole_workbook(cell, xml, code):
    with pytest.raises(WorkbookBaselineError, match=code):
        parse_workbook_baseline(workbook(change={cell: xml}), layout=layout())


def test_penny_tolerance_and_optional_group_cost_disclosure():
    mapped = layout()
    specs = list(mapped.observations)
    specs[1] = replace(specs[1], groups=(GroupCells("Alpha", "D6"), GroupCells("Beta", "F6")))
    result = parse_workbook_baseline(
        workbook(change={"B6": '<c r="B6"><v>300.1334567890123456789</v></c>'}),
        layout=replace(mapped, observations=tuple(specs)),
    )
    assert result.observations[1]["invested_reconciled"] is False


@pytest.mark.parametrize(
    "mapped,code",
    [
        (
            replace(layout(), observations=layout().observations[:5]),
            "six_observation_mapping_required",
        ),
        (replace(layout(), sheet="Missing"), "baseline_sheet_unavailable"),
        (
            replace(layout(), observations=(layout().observations[0],) * 6),
            "duplicate_observation_mapping",
        ),
        (
            replace(
                layout(),
                observations=(replace(layout().observations[0], date_precision="year"),)
                + layout().observations[1:],
            ),
            "invalid_date_precision",
        ),
    ],
)
def test_invalid_mapping_is_explicit(mapped, code):
    with pytest.raises(WorkbookBaselineError, match=code):
        parse_workbook_baseline(workbook(), layout=mapped)


def test_zip_corruption_and_dtd_are_rejected_safely():
    with pytest.raises(WorkbookBaselineError, match="invalid_workbook"):
        parse_workbook_baseline(b"not a workbook", layout=layout())
    content = workbook(change={"D6": '<!DOCTYPE x [<!ENTITY x "secret">]>'})
    with pytest.raises(WorkbookBaselineError, match="unsafe_xml"):
        parse_workbook_baseline(content, layout=layout())


def test_month_precision_preserves_period_without_inventing_a_day():
    mapped = layout()
    first = replace(
        mapped.observations[0], observed_on=None, observed_month="2026-05", date_precision="month"
    )
    result = parse_workbook_baseline(
        workbook(), layout=replace(mapped, observations=(first,) + mapped.observations[1:])
    )
    observation = result.observations[0]
    assert observation["observed_on"] is None
    assert observation["observed_month"] == "2026-05"
    assert observation["date_precision"] == "month"
    assert observation["date_basis"] == "verified_layout_mapping"


@pytest.mark.parametrize("period", ["2026-13", "2026-1", "unknown", "2026-05-01"])
def test_invalid_month_precision_mapping_is_rejected(period):
    mapped = layout()
    first = replace(
        mapped.observations[0], observed_on=None, observed_month=period, date_precision="month"
    )
    with pytest.raises(WorkbookBaselineError, match="invalid_observation_date"):
        parse_workbook_baseline(
            workbook(), layout=replace(mapped, observations=(first,) + mapped.observations[1:])
        )


@pytest.fixture
def engine(tmp_path):
    path = tmp_path / "synthetic.db"
    upgrade_database(path)
    db = create_db_engine(path)
    with Session(db) as session, session.begin():
        session.add_all(
            [Account(id="demo", environment="demo"), Account(id="live", environment="live")]
        )
    yield db
    db.dispose()


def accept(engine, **overrides):
    return import_workbook_baseline(
        engine,
        **(
            {
                "account_id": "demo",
                "content": workbook(),
                "layout": layout(),
                "clock": lambda: NOW,
            }
            | overrides
        ),
    )


def test_atomic_acceptance_repeat_and_new_version_keep_immutable_private_sources(engine):
    first = accept(engine)
    assert first.status == "succeeded"
    assert first.counts["observations"] == 6
    assert first.counts["economic_events_added"] == 0
    assert accept(engine).status == "duplicate"
    assert accept(engine, account_id="live").status == "succeeded"
    revised = workbook(change={"H6": '<c r="H6" t="inlineStr"><is><t>Revision</t></is></c>'})
    assert accept(engine, content=revised).status == "succeeded"
    with Session(engine) as session:
        sources = session.scalars(select(SourceRecord)).all()
        assert len(sources) == 18
        assert len(session.scalars(select(AuditRecord)).all()) == 3
        source = session.scalars(
            select(SourceRecord).where(
                SourceRecord.run_id == first.run_id,
                SourceRecord.row_number == 1,
            )
        ).one()
        payload = json.loads(source.payload_json)
        assert payload["import_run"] == first.run_id
        assert payload["file_hash"] == session.get(ImportRun, first.run_id).content_hash
        assert Decimal(payload["observation"]["value"]) == Decimal("100.1234567890123456789")


def test_failure_rolls_back_all_sources_and_audit_then_retry_succeeds(engine):
    def fail(*_args):
        raise RuntimeError("Private data must never reach logs")

    event.listen(SourceRecord, "after_insert", fail)
    try:
        report = accept(engine)
    finally:
        event.remove(SourceRecord, "after_insert", fail)
    assert report.status == "failed"
    assert report.safe_error == "import_storage_failed"
    with Session(engine) as session:
        assert session.scalars(select(SourceRecord)).all() == []
        assert session.scalars(select(AuditRecord)).all() == []
        assert session.get(ImportRun, report.run_id).error_code == "import_storage_failed"
    assert accept(engine).status == "succeeded"


def test_duplicate_acceptance_race_has_no_orphan_sources(engine, monkeypatch):
    original = workbook_import.parse_workbook_baseline
    nested = False

    def racing(*args, **kwargs):
        nonlocal nested
        if not nested:
            nested = True
            assert accept(engine).status == "succeeded"
        return original(*args, **kwargs)

    monkeypatch.setattr(workbook_import, "parse_workbook_baseline", racing)
    assert accept(engine).status == "duplicate"
    with Session(engine) as session:
        assert len(session.scalars(select(SourceRecord)).all()) == 6
        assert len(session.scalars(select(AuditRecord)).all()) == 1


def test_failed_parse_has_safe_durable_attempt(engine):
    report = accept(engine, content=b"bad confidential source")
    assert report.status == "failed"
    assert report.safe_error == "invalid_workbook"
    with Session(engine) as session:
        assert session.get(ImportRun, report.run_id).status == "failed"
        assert session.scalars(select(SourceRecord)).all() == []
