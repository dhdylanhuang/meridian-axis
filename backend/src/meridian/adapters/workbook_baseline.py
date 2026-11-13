"""Read explicitly mapped Excel baseline cells without evaluating or saving a workbook."""

import io
import posixpath
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from xml.etree import ElementTree

from meridian.persistence.types import decimal_text

SCHEMA_VERSION = "excel-baseline-v1"
MAX_BYTES = 10 * 1024 * 1024
MAX_EXPANDED_BYTES = 50 * 1024 * 1024
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CELL_ADDRESS = re.compile(r"[A-Z]{1,3}[1-9][0-9]{0,6}\Z")
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


class WorkbookBaselineError(ValueError):
    """Stable diagnostics contain no workbook paths, contents or financial values."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class GroupCells:
    name: str
    value: str | None
    invested: str | None = None


@dataclass(frozen=True)
class ObservationCells:
    label: str
    value: str
    invested: str
    groups: tuple[GroupCells, ...]
    observed_on: date | None = None
    date_precision: str = "unknown"
    notes: str | None = None
    cumulative_dividends: str | None = None
    observed_month: str | None = None


@dataclass(frozen=True)
class WorkbookBaselineLayout:
    sheet: str
    observations: tuple[ObservationCells, ...]


@dataclass(frozen=True)
class WorkbookBaseline:
    observations: tuple[dict, ...]
    sheet: str
    schema_version: str = SCHEMA_VERSION
    currency: str = "GBP"


def _xml(content: bytes):
    # OOXML UTF-8 XML is supported. Decode before the declaration check so an
    # alternate byte encoding cannot hide an entity declaration from the guard.
    text = content.decode("utf-8-sig")
    if "\x00" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise WorkbookBaselineError("unsafe_xml")
    return ElementTree.fromstring(text)


def _texts(element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{{{MAIN_NS}}}t"))


def _cells(content: bytes, sheet: str) -> dict[str, dict]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if (
            len(entries) > 1024
            or len(names) != len(set(names))
            or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES
            or any(entry.flag_bits & 1 for entry in entries)
        ):
            raise WorkbookBaselineError("unsupported_archive")
        workbook = _xml(archive.read("xl/workbook.xml"))
        relations = _xml(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {}
        for relation in relations.findall(f"{{{REL_NS}}}Relationship"):
            if relation.get("TargetMode") == "External":
                raise WorkbookBaselineError("external_workbook_relationship")
            target = relation.get("Target", "")
            resolved = posixpath.normpath(
                target.lstrip("/") if target.startswith("/") else "xl/" + target
            )
            if not resolved.startswith("xl/") or "\\" in resolved:
                raise WorkbookBaselineError("invalid_workbook_relationship")
            targets[relation.get("Id")] = resolved
        matches = [
            node
            for node in workbook.findall(f"{{{MAIN_NS}}}sheets/{{{MAIN_NS}}}sheet")
            if node.get("name") == sheet
        ]
        if len(matches) != 1:
            raise WorkbookBaselineError("baseline_sheet_unavailable")
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = [
                _texts(node)
                for node in _xml(archive.read("xl/sharedStrings.xml")).findall(f"{{{MAIN_NS}}}si")
            ]
        relationship = matches[0].get(f"{{{DOC_REL_NS}}}id")
        root = _xml(archive.read(targets[relationship]))
        cells = {}
        for cell in root.findall(f"{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row/{{{MAIN_NS}}}c"):
            address = cell.get("r", "")
            if not CELL_ADDRESS.fullmatch(address) or address in cells:
                raise WorkbookBaselineError("invalid_cell_address")
            value = cell.find(f"{{{MAIN_NS}}}v")
            formula = cell.find(f"{{{MAIN_NS}}}f")
            kind = cell.get("t", "n")
            raw = None if value is None else value.text
            if kind == "s" and raw is not None:
                index = int(raw)
                if index < 0:
                    raise WorkbookBaselineError("invalid_shared_string")
                text = shared[index]
            elif kind == "inlineStr":
                text = _texts(cell)
            else:
                text = raw
            cells[address] = {
                "type": kind,
                "raw_value": raw,
                "text": text,
                "formula": None if formula is None else formula.text or "",
            }
        return cells


def _cell(cells: dict, address: str) -> dict:
    if not isinstance(address, str) or not CELL_ADDRESS.fullmatch(address):
        raise WorkbookBaselineError("invalid_cell_mapping")
    if address not in cells:
        raise WorkbookBaselineError("mapped_cell_missing")
    return cells[address]


def _number(cells: dict, address: str) -> Decimal:
    cell = _cell(cells, address)
    raw = cell["raw_value"]
    if cell["type"] != "n" or raw is None or not NUMBER.fullmatch(raw) or len(raw) > 64:
        raise WorkbookBaselineError("numeric_cell_or_cache_required")
    value = Decimal(raw)
    if not value.is_finite() or abs(value.adjusted()) > 30 or value < 0:
        raise WorkbookBaselineError("invalid_baseline_amount")
    return value


def _observation(cells: dict, spec: ObservationCells) -> dict:
    if spec.date_precision not in {"day", "month", "unknown"}:
        raise WorkbookBaselineError("invalid_date_precision")
    if (spec.observed_on is not None) != (spec.date_precision == "day"):
        raise WorkbookBaselineError("invalid_observation_date")
    if spec.observed_on is not None and type(spec.observed_on) is not date:
        raise WorkbookBaselineError("invalid_observation_date")
    if (spec.observed_month is not None) != (spec.date_precision == "month"):
        raise WorkbookBaselineError("invalid_observation_date")
    if spec.observed_month is not None:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", spec.observed_month):
            raise WorkbookBaselineError("invalid_observation_date")
        try:
            date.fromisoformat(spec.observed_month + "-01")
        except ValueError:
            raise WorkbookBaselineError("invalid_observation_date") from None
    label = _cell(cells, spec.label)["text"]
    if not isinstance(label, str) or not label.strip():
        raise WorkbookBaselineError("observation_label_required")
    if not spec.groups or len({group.name for group in spec.groups}) != len(spec.groups):
        raise WorkbookBaselineError("invalid_group_mapping")
    total_value = _number(cells, spec.value)
    invested = _number(cells, spec.invested)
    addresses = [spec.label, spec.value, spec.invested]
    groups = []
    values = []
    costs = []
    missing = []
    for group in spec.groups:
        if not isinstance(group.name, str) or not group.name.strip():
            raise WorkbookBaselineError("invalid_group_mapping")
        if group.value is None:
            if group.invested is not None:
                raise WorkbookBaselineError("invalid_group_mapping")
            missing.append(group.name)
            groups.append({"name": group.name, "value": None, "invested": None})
            continue
        value = _number(cells, group.value)
        values.append(value)
        addresses.append(group.value)
        cost = None
        if group.invested is not None:
            cost = _number(cells, group.invested)
            costs.append(cost)
            addresses.append(group.invested)
        groups.append(
            {
                "name": group.name,
                "value": decimal_text(value),
                "invested": (None if cost is None else decimal_text(cost)),
            }
        )
    with localcontext() as context:
        context.prec = 80
        if abs(sum(values, Decimal(0)) - total_value) > Decimal("0.01"):
            raise WorkbookBaselineError("baseline_value_mismatch")
        invested_reconciled = len(costs) == len(values)
        if invested_reconciled and abs(sum(costs, Decimal(0)) - invested) > Decimal("0.01"):
            raise WorkbookBaselineError("baseline_invested_mismatch")
    notes = None
    dividends = None
    if spec.notes is not None:
        notes = _cell(cells, spec.notes)["text"]
        addresses.append(spec.notes)
    if spec.cumulative_dividends is not None:
        dividends = decimal_text(_number(cells, spec.cumulative_dividends))
        addresses.append(spec.cumulative_dividends)
    if len(set(addresses)) != len(addresses):
        raise WorkbookBaselineError("overlapping_cell_mapping")
    return {
        "provenance": "excel_migration",
        "label": label,
        "observed_on": None if spec.observed_on is None else spec.observed_on.isoformat(),
        "observed_month": spec.observed_month,
        "date_precision": spec.date_precision,
        "date_basis": (
            "unknown" if spec.date_precision == "unknown" else "verified_layout_mapping"
        ),
        "value": decimal_text(total_value),
        "recorded_invested": decimal_text(invested),
        "invested_basis": "recorded_holding_cost",
        "invested_reconciled": invested_reconciled,
        "groups": groups,
        "coverage": "incomplete" if missing else "mapped_groups",
        "missing_groups": missing,
        "notes": notes,
        "cumulative_dividends": dividends,
        "dividend_basis": "cumulative_observation_coverage_unknown",
        "raw_cells": {address: cells[address] for address in addresses},
    }


def parse_workbook_baseline(
    content: bytes,
    *,
    layout: WorkbookBaselineLayout,
    currency: str = "GBP",
) -> WorkbookBaseline:
    """Import six explicitly mapped observations with source cache and penny controls.

    Dates are explicit verified mapping metadata. Unknown dates stay absent.
    Formula results must already be cached in the source. Group invested cells
    are optional because the historical table may record only portfolio cost.
    """
    if not isinstance(content, bytes):
        raise WorkbookBaselineError("content_must_be_bytes")
    if len(content) > MAX_BYTES:
        raise WorkbookBaselineError("file_too_large")
    if currency != "GBP":
        raise WorkbookBaselineError("baseline_requires_gbp")
    if (
        not isinstance(layout, WorkbookBaselineLayout)
        or not isinstance(layout.sheet, str)
        or not layout.sheet.strip()
        or len(layout.observations) != 6
    ):
        raise WorkbookBaselineError("six_observation_mapping_required")
    try:
        cells = _cells(content, layout.sheet)
        observations = tuple(_observation(cells, spec) for spec in layout.observations)
        labels = [spec.label for spec in layout.observations]
        if len(set(labels)) != len(labels):
            raise WorkbookBaselineError("duplicate_observation_mapping")
    except WorkbookBaselineError:
        raise
    except Exception:
        raise WorkbookBaselineError("invalid_workbook") from None
    return WorkbookBaseline(observations=observations, sheet=layout.sheet)
