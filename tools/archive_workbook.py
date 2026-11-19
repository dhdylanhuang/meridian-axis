"""Manual, incremental broker archive. Standard library only; never edits legacy sheets."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("", S)
Q = lambda name: "{" + S + "}" + name
NAME = "AXIS Archive"
HEADERS = [
    "Observed UTC",
    "Portfolio GBP",
    "Available cash GBP",
    "Investments GBP",
    "Unrealised PnL GBP",
    "Snapshot ID",
    "Created UTC",
    "Import ID",
    "Archive SHA-256",
    "JSON parts",
]


class ArchiveError(ValueError):
    pass


CHUNK = 15000  # At most 30,000 UTF-16 units, below Excel's 32,767-cell limit.


def col(n):
    value = ""
    while n:
        n, r = divmod(n - 1, 26)
        value = chr(65 + r) + value
    return value


def cell_values(row, strings=()):
    result = {}
    for c in row.findall(Q("c")):
        v = c.find(Q("v"))
        value = (
            "".join(t.text or "" for t in c.iter(Q("t")))
            if c.get("t") == "inlineStr"
            else v.text
            if v is not None
            else ""
        )
        if c.get("t") == "s":
            value = strings[int(value)]
        result[re.sub(r"\d", "", c.get("r"))] = value
    return result


def shared_strings(book):
    if "xl/sharedStrings.xml" not in book.namelist():
        return []
    if book.getinfo("xl/sharedStrings.xml").file_size > 256 * 1024 * 1024:
        raise ArchiveError("archive_strings_too_large_use_another_workbook")
    values = []
    with book.open("xl/sharedStrings.xml") as stream:
        for event, element in ET.iterparse(stream, events=("end",)):
            if element.tag == Q("si"):
                values.append("".join(t.text or "" for t in element.iter(Q("t"))))
                element.clear()
    return values


def row_xml(number, values, styles):
    row = ET.Element(Q("row"), r=str(number), ht="22", customHeight="1")
    for i, value in enumerate(values, 1):
        if value is None:
            continue
        attrs = {"r": f"{col(i)}{number}", "s": styles.get(col(i), "0")}
        c = ET.SubElement(row, Q("c"), attrs)
        if isinstance(value, (float, int)):
            ET.SubElement(c, Q("v")).text = str(value)
        else:
            c.set("t", "inlineStr")
            ET.SubElement(
                ET.SubElement(c, Q("is")),
                Q("t"),
                {"{http://www.w3.org/XML/1998/namespace}space": "preserve"},
            ).text = str(value)
    return ET.tostring(row)


def extend_styles(original, source):
    """Append styles; never renumber or replace existing workbook styles."""
    target, src = ET.fromstring(original), ET.fromstring(source)
    offsets, formats = {}, {}
    for tag in ("fonts", "fills", "borders"):
        offsets[tag] = len(target.find(Q(tag)))
    existing = target.find(Q("numFmts"))
    next_id = (
        max(
            [163]
            + [
                int(x.get("numFmtId"))
                for x in (existing if existing is not None else [])
            ]
        )
        + 1
    )
    for item in src.find(Q("numFmts")) if src.find(Q("numFmts")) is not None else []:
        old = int(item.get("numFmtId"))
        formats[old] = next_id
        item.set("numFmtId", str(next_id))
        next_id += 1
    base = len(target.find(Q("cellXfs")))
    for item in src.find(Q("cellXfs")):
        for key, tag in [
            ("fontId", "fonts"),
            ("fillId", "fills"),
            ("borderId", "borders"),
        ]:
            item.set(key, str(int(item.get(key, "0")) + offsets[tag]))
        item.set(
            "numFmtId",
            str(
                formats.get(
                    int(item.get("numFmtId", "0")), int(item.get("numFmtId", "0"))
                )
            ),
        )
        item.set("xfId", "0")
    text = original.decode()
    for tag in ("numFmts", "fonts", "fills", "borders", "cellXfs"):
        items = list(src.find(Q(tag))) if src.find(Q(tag)) is not None else []
        if not items:
            continue
        added = "".join(ET.tostring(x, encoding="unicode") for x in items)
        pattern = rf"(<{tag}\b[^>]*>)(.*?)(</{tag}>)"
        match = re.search(pattern, text, re.S)
        if match:
            old_count = len(target.find(Q(tag)))
            opening = re.sub(
                r'count="\d+"', f'count="{old_count + len(items)}"', match[1]
            )
            text = (
                text[: match.start()]
                + opening
                + match[2]
                + added
                + match[3]
                + text[match.end() :]
            )
        else:
            empty = re.search(rf"<{tag}\b[^>]*/>", text)
            block = f'<{tag} count="{len(items)}">{added}</{tag}>'
            if empty:
                text = text[: empty.start()] + block + text[empty.end() :]
            else:
                text = text.replace("<fonts", block + "<fonts", 1)
    return text.encode(), base


def add_before_close(data, tag, element):
    text = data.decode()
    marker = re.search(rf"</(?:\w+:)?{tag}>", text)
    if not marker:
        raise ArchiveError("workbook_structure_unsupported")
    return (
        text[: marker.start()]
        + ET.tostring(element, encoding="unicode")
        + text[marker.start() :]
    ).encode()


def source_pages(config, cursor):
    cli = Path(config["cli"]).resolve()
    project = config["project"]
    if not re.fullmatch("[a-z]{20}", project):
        raise ArchiveError("project_invalid")
    while True:
        quoted = lambda x: "'" + str(x).replace("'", "''") + "'"
        predicate = (
            ""
            if cursor is None
            else f" AND (s.created_at,s.id)>({quoted(cursor[0])},{quoted(cursor[1])})"
        )
        sql = f"""SELECT s.id,s.created_at,s.observed_at,s.source_run_id,s.snapshot_json,
 s.digest AS snapshot_digest,src.id AS source_id,src.schema_version,src.payload_json,
 src.digest AS source_digest FROM public.broker_snapshots s
 JOIN public.import_log r ON r.id=s.source_run_id AND r.account_id=s.account_id
 JOIN public.source_records src ON src.run_id=r.id AND src.account_id=r.account_id
 WHERE s.account_id='shared-isa' AND r.kind='trading212_refresh' AND r.status='succeeded'
 AND src.kind='trading212_refresh' AND src.row_number=1 {predicate}
 ORDER BY s.created_at,s.id LIMIT 50"""
        result = subprocess.run(
            [
                str(cli),
                "db",
                "query",
                f"--remote={project}",
                "--file",
                "/dev/stdin",
                "--read-only",
                "--output-format",
                "json",
                "--log-level",
                "none",
            ],
            input=sql.encode(),
            capture_output=True,
            timeout=60,
        )
        if result.returncode:
            raise ArchiveError("archive_source_unavailable")
        rows = json.loads(result.stdout)["rows"]
        if not rows:
            return
        yield rows
        cursor = (rows[-1]["created_at"], rows[-1]["id"])
        if len(rows) < 50:
            return


def archive(config, pages=source_pages):
    workbook, template = (
        Path(config["workbook"]).resolve(),
        Path(config["template"]).resolve(),
    )
    if workbook.with_name("~$" + workbook.name).exists():
        raise ArchiveError("close_workbook_first")
    fingerprint = hashlib.sha256(workbook.read_bytes()).digest()
    seen, cursor, count, max_parts, modified = set(), None, 0, 5, {}
    temp_paths = []
    try:
        with zipfile.ZipFile(workbook) as original:
            book = ET.fromstring(original.read("xl/workbook.xml"))
            properties = book.find(Q("workbookPr"))
            date_offset = (
                1462
                if properties is not None
                and properties.get("date1904") in {"1", "true"}
                else 0
            )
            rels = ET.fromstring(original.read("xl/_rels/workbook.xml.rels"))
            existing = next(
                (x for x in book.find(Q("sheets")) if x.get("name") == NAME), None
            )
            if existing is None:
                with zipfile.ZipFile(template) as model:
                    style_xml, offset = extend_styles(
                        original.read("xl/styles.xml"), model.read("xl/styles.xml")
                    )
                    modified["xl/styles.xml"] = style_xml
                    sheet = ET.fromstring(model.read("xl/worksheets/sheet1.xml"))
                    strings = []
                    if "xl/sharedStrings.xml" in model.namelist():
                        strings = [
                            "".join(x.itertext())
                            for x in ET.fromstring(model.read("xl/sharedStrings.xml"))
                        ]
                    for c in sheet.iter(Q("c")):
                        c.set("s", str(int(c.get("s", "0")) + offset))
                        if c.get("t") == "s":
                            value = strings[int(c.find(Q("v")).text)]
                            c.remove(c.find(Q("v")))
                            c.set("t", "inlineStr")
                            ET.SubElement(
                                ET.SubElement(c, Q("is")), Q("t")
                            ).text = value
                number = max(int(x.get("sheetId")) for x in book.find(Q("sheets"))) + 1
                sheet_path, relation_id = (
                    f"xl/worksheets/axisArchive{number}.xml",
                    f"rIdAxisArchive{number}",
                )
                modified["xl/workbook.xml"] = add_before_close(
                    original.read("xl/workbook.xml"),
                    "sheets",
                    ET.Element(
                        Q("sheet"),
                        {
                            "name": NAME,
                            "sheetId": str(number),
                            f"{{{R}}}id": relation_id,
                        },
                    ),
                )
                modified["xl/_rels/workbook.xml.rels"] = add_before_close(
                    original.read("xl/_rels/workbook.xml.rels"),
                    "Relationships",
                    ET.Element(
                        "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
                        Id=relation_id,
                        Type=R + "/worksheet",
                        Target=sheet_path[3:],
                    ),
                )
                modified["[Content_Types].xml"] = add_before_close(
                    original.read("[Content_Types].xml"),
                    "Types",
                    ET.Element(
                        "{http://schemas.openxmlformats.org/package/2006/content-types}Override",
                        PartName="/" + sheet_path,
                        ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
                    ),
                )
                data = ET.tostring(sheet)
                archive_strings = []
            else:
                target = next(
                    x.get("Target")
                    for x in rels
                    if x.get("Id") == existing.get(f"{{{R}}}id")
                )
                sheet_path = (
                    target.lstrip("/") if target.startswith("/") else "xl/" + target
                )
                if original.getinfo(sheet_path).file_size > 256 * 1024 * 1024:
                    raise ArchiveError("archive_sheet_too_large_use_another_workbook")
                data = original.read(sheet_path)
                archive_strings = shared_strings(original)
            # Only the dedicated archive is parsed; legacy sheet parts are copied unchanged.
            root = ET.fromstring(data)
            body = root.find(Q("sheetData"))
            styles, header_styles = {}, {}
            fd, body_path = tempfile.mkstemp(dir=workbook.parent, prefix=".axis-rows-")
            temp_paths.append(body_path)
            with os.fdopen(fd, "wb") as out:
                for row in list(body):
                    values = cell_values(row, archive_strings)
                    n = int(row.get("r"))
                    if n == 5:
                        if (
                            values.get("F") != "Snapshot ID"
                            or values.get("I") != "Archive SHA-256"
                        ):
                            raise ArchiveError("archive_sheet_format_invalid")
                        header_styles = {
                            col(i): row[0].get("s", "0") for i in range(1, 523)
                        }
                    if n == 6:
                        styles = {
                            re.sub(r"\d", "", c.get("r")): c.get("s", "0") for c in row
                        }
                    if n < 6:
                        continue
                    if not values.get("F"):
                        continue
                    parts = int(values["J"])
                    package = "".join(values.get(col(11 + i), "") for i in range(parts))
                    if hashlib.sha256(package.encode()).hexdigest() != values["I"]:
                        raise ArchiveError("existing_archive_checksum_failed")
                    record = json.loads(package)
                    if record["id"] in seen:
                        raise ArchiveError("duplicate_archive_id")
                    seen.add(record["id"])
                    count += 1
                    max_parts = max(max_parts, parts)
                    cursor = max(
                        cursor or ("", ""), (record["created_at"], record["id"])
                    )
                    out.write(ET.tostring(row))
                before = count
                for batch in pages(config, cursor):
                    for record in batch:
                        if record["id"] in seen:
                            continue
                        for field, digest in [
                            ("snapshot_json", "snapshot_digest"),
                            ("payload_json", "source_digest"),
                        ]:
                            if (
                                hashlib.sha256(record[field].encode()).hexdigest()
                                != record[digest]
                            ):
                                raise ArchiveError("source_checksum_failed")
                        package = json.dumps(
                            record, ensure_ascii=False, separators=(",", ":")
                        )
                        chunks = [
                            package[i : i + CHUNK]
                            for i in range(0, len(package), CHUNK)
                        ]
                        if len(chunks) > 512 or count >= 1_048_570:
                            raise ArchiveError("excel_archive_capacity_reached")
                        value = json.loads(record["snapshot_json"])
                        from datetime import datetime

                        stamp = (
                            datetime.fromisoformat(record["observed_at"]).timestamp()
                            / 86400
                            + 25569
                            - date_offset
                        )
                        number = lambda x: None if x is None else float(x)
                        summary = [
                            stamp,
                            number(value.get("total_value")),
                            number(
                                value.get("cash_components", {}).get("availableToTrade")
                            ),
                            number(value.get("investments", {}).get("currentValue")),
                            number(
                                value.get("investments", {}).get("unrealizedProfitLoss")
                            ),
                            record["id"],
                            record["created_at"],
                            record["source_run_id"],
                            hashlib.sha256(package.encode()).hexdigest(),
                            len(chunks),
                        ]
                        count += 1
                        seen.add(record["id"])
                        max_parts = max(max_parts, len(chunks))
                        out.write(row_xml(count + 5, summary + chunks, styles))
            if before == count and existing is not None:
                return {"added": 0, "total": count}
            for row in list(body):
                body.remove(row)
            # Rebuild only archive-owned rows; template top notes remain unchanged.
            source_root = ET.fromstring(data)
            for row in source_root.find(Q("sheetData")):
                if int(row.get("r")) < 5:
                    body.append(copy.deepcopy(row))
            header = ET.fromstring(
                row_xml(
                    5,
                    HEADERS + [f"Exact JSON {i + 1}" for i in range(max_parts)],
                    header_styles,
                )
            )
            body.append(header)
            dim = root.find(Q("dimension"))
            if dim is not None:
                dim.set("ref", f"A1:{col(10 + max_parts)}{max(6, count + 5)}")
            xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            closing = b"</sheetData>"
            if closing not in xml:
                raise ArchiveError("archive_xml_unsupported")
            prefix, tail = xml.split(closing, 1)
            fd, staged = tempfile.mkstemp(
                dir=workbook.parent, prefix=".axis-archive-", suffix=".xlsx"
            )
            os.close(fd)
            temp_paths.append(staged)
            with zipfile.ZipFile(
                staged, "w", compression=zipfile.ZIP_DEFLATED
            ) as output:
                for entry in original.infolist():
                    if entry.filename == sheet_path:
                        continue
                    if entry.filename in modified:
                        output.writestr(entry, modified[entry.filename])
                    else:
                        with (
                            original.open(entry) as src,
                            output.open(entry, "w") as dst,
                        ):
                            shutil.copyfileobj(src, dst, 1024 * 1024)
                for key, content in modified.items():
                    if key not in original.namelist():
                        output.writestr(key, content)
                with output.open(sheet_path, "w") as dst:
                    dst.write(prefix)
                    with open(body_path, "rb") as src:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                    dst.write(closing + tail)
            with zipfile.ZipFile(staged) as check:
                for entry in original.infolist():
                    if entry.filename not in modified and entry.filename != sheet_path:
                        saved = check.getinfo(entry.filename)
                        if (saved.CRC, saved.file_size) != (entry.CRC, entry.file_size):
                            raise ArchiveError("legacy_part_changed")
            if hashlib.sha256(workbook.read_bytes()).digest() != fingerprint:
                raise ArchiveError("workbook_changed_during_export")
            backup = Path(config["backup"])
            if not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                with backup.open("xb") as dst, workbook.open("rb") as src:
                    shutil.copyfileobj(src, dst)
                backup.chmod(0o600)
            os.replace(staged, workbook)
            return {
                "added": count - before,
                "total": count,
                "legacy_parts_preserved": True,
            }
    finally:
        for path in temp_paths:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(archive(json.loads(args.config.read_text()))))
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "category": str(error)
                    if isinstance(error, ArchiveError)
                    else type(error).__name__,
                }
            )
        )
        raise SystemExit(1)
