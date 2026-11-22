"""Read Excel .xlsx rows with Python stdlib (streaming, read-only).

The delivery workbook is too large for some in-memory spreadsheet readers.
This parser preserves literal cell values and Excel row numbers for auditing.
This module deliberately does not modify user-owned Excel workbooks.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _column_number(cell_address: str) -> int:
    letters = "".join(ch for ch in cell_address if ch.isalpha()).upper()
    out = 0
    for ch in letters:
        out = out * 26 + ord(ch) - ord("A") + 1
    return out - 1


def _load_shared_strings(z: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    strings: list[str] = []
    with z.open("xl/sharedStrings.xml") as fh:
        for _, element in ET.iterparse(fh, events=("end",)):
            if element.tag == f"{_MAIN}si":
                strings.append("".join(n.text or "" for n in element.iter(f"{_MAIN}t")))
                element.clear()
    return strings


def _cell_value(cell: ET.Element, shared_strings: list[str]):
    typ = cell.get("t")
    if typ == "inlineStr":
        part = cell.find(f"{_MAIN}is")
        return "" if part is None else "".join(t.text or "" for t in part.iter(f"{_MAIN}t"))
    node = cell.find(f"{_MAIN}v")
    if node is None or node.text is None:
        return None
    s = node.text
    if typ == "s":
        return shared_strings[int(s)]
    if typ == "b":
        return s == "1"
    if typ in ("str", "e", "d"):
        return s
    try:
        number = float(s)
        return int(number) if number.is_integer() else number
    except ValueError:
        return s


def rows(path: str | Path) -> Iterator[dict]:
    """Yield dicts with `excel_row` and `fields` for nonempty rows.

    Supports the first worksheet, formulas with cached results, shared/inline strings.
    Excel dates are returned as numeric serials, then converted in the ETL mapping.
    """
    with ZipFile(path) as z:
        strings = _load_shared_strings(z)
        sheets = sorted(p for p in z.namelist()
                        if p.startswith("xl/worksheets/sheet") and p.endswith(".xml"))
        if not sheets:
            raise ValueError(f"No worksheet found in {path}")
        with z.open(sheets[0]) as fh:
            context = ET.iterparse(fh, events=("start", "end"))
            _, root = next(context)
            header: list[str] | None = None
            for event, element in context:
                if event != "end" or element.tag != f"{_MAIN}row":
                    continue
                by_column: dict[int, object] = {}
                for c in element.findall(f"{_MAIN}c"):
                    col = _column_number(c.get("r", ""))
                    by_column[col] = _cell_value(c, strings)
                if header is None:
                    max_col = max(by_column, default=-1)
                    header = [str(by_column.get(i) or "").strip() for i in range(max_col + 1)]
                    if not any(header):
                        raise ValueError("No header found in first row")
                else:
                    fields = {h: by_column.get(i) for i, h in enumerate(header) if h}
                    if any(v is not None and v != "" for v in fields.values()):
                        yield {"excel_row": int(element.get("r") or 0), "fields": fields}
                element.clear()
                root.clear()


def headers(path: str | Path) -> list[str]:
    with ZipFile(path) as z:
        shared = _load_shared_strings(z)
        with z.open("xl/worksheets/sheet1.xml") as fh:
            for _, element in ET.iterparse(fh, events=("end",)):
                if element.tag == f"{_MAIN}row":
                    by_column = {_column_number(c.get("r", "")): _cell_value(c, shared)
                                 for c in element.findall(f"{_MAIN}c")}
                    return [str(by_column.get(i) or "").strip()
                            for i in range(max(by_column, default=-1) + 1)]
    return []
