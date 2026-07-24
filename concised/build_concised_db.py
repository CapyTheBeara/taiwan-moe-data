#!/usr/bin/env python3
"""
build_concised_db.py — Convert dict_concised_*.zip (MOE 國語辭典簡編本 xlsx
download) into concised.db (SQLite), analogous to kautian.db.

Stdlib-only (zipfile + xml.etree.ElementTree) — no openpyxl/pandas dependency.
The xlsx is itself a zip container; sharedStrings.xml holds all string cell
values (OOXML escapes control chars as _xHHHH_, unescaped here), sheet1.xml
holds the row/cell grid referencing those strings by index.

Usage:
    python3 build_concised_db.py <path-to-dict_concised_*.zip> <path-to-concised.db>
"""

import re
import sqlite3
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

COLUMNS = [
    "字詞名",
    "字詞號",
    "部首字",
    "總筆畫數",
    "部首外筆畫數",
    "多音排序",
    "注音一式",
    "變體類型",
    "變體注音",
    "漢語拼音",
    "變體漢語拼音",
    "相似詞",
    "相反詞",
    "釋義",
    "多音參見訊息",
]


def unescape_ooxml(s: str) -> str:
    return re.sub(r"_x([0-9A-Fa-f]{4})_", lambda m: chr(int(m.group(1), 16)), s)


def find_inner_xlsx_bytes(outer_zip_path: Path) -> bytes:
    with zipfile.ZipFile(outer_zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".xlsx")]
        if len(names) != 1:
            raise ValueError(f"expected exactly one .xlsx in {outer_zip_path}, found {names}")
        return zf.read(names[0])


def col_letters_to_index(ref: str) -> int:
    """'N5' -> 13 (0-based column index)."""
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def parse_xlsx_rows(xlsx_bytes: bytes) -> list[list[str]]:
    import io

    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zf:
        sst_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        shared_strings = [
            unescape_ooxml("".join(t.text or "" for t in si.iter(NS + "t")))
            for si in sst_root
        ]
        sheet_root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))

    sheet_data = sheet_root.find(NS + "sheetData")
    rows_out = []
    width = len(COLUMNS)
    for row in sheet_data.findall(NS + "row"):
        # Cells with empty values are frequently omitted from the XML entirely
        # (sparse), so alignment MUST come from each cell's own "r" reference
        # (e.g. "N5" -> column 13), never from positional order in the row.
        vals = [""] * width
        for cell in row.findall(NS + "c"):
            idx = col_letters_to_index(cell.get("r"))
            if idx >= width:
                continue
            v = cell.find(NS + "v")
            if v is None:
                continue
            if cell.get("t") == "s":
                vals[idx] = shared_strings[int(v.text)]
            else:
                vals[idx] = v.text or ""
        rows_out.append(vals)
    return rows_out


def build_db(rows: list[list[str]], db_path: Path) -> int:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    cols_sql = ", ".join(f'"{c}" TEXT' for c in COLUMNS)
    conn.execute(f"CREATE TABLE concised ({cols_sql})")

    header, *data_rows = rows
    assert len(header) == len(COLUMNS), f"unexpected header width: {header}"

    placeholders = ", ".join("?" for _ in COLUMNS)
    n = 0
    for r in data_rows:
        conn.execute(f"INSERT INTO concised VALUES ({placeholders})", r)
        n += 1

    conn.execute('CREATE INDEX idx_concised_ziciming ON concised("字詞名")')
    conn.commit()
    conn.close()
    return n


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    src_zip = Path(sys.argv[1])
    db_path = Path(sys.argv[2])

    print(f"[info] reading {src_zip}", file=sys.stderr)
    xlsx_bytes = find_inner_xlsx_bytes(src_zip)
    rows = parse_xlsx_rows(xlsx_bytes)
    print(f"[info] parsed {len(rows) - 1} data rows", file=sys.stderr)

    n = build_db(rows, db_path)
    print(f"[info] wrote {n} rows to {db_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
