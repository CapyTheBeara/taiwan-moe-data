#!/usr/bin/env python3
"""
build_web_json.py — Build the browser document: JSON small enough to ship whole,
that decodes with `kautian/web/kautian.mjs` and no other dependency.

The dataset can come from the .db, from a KTJSON1 document, or from the
container — the output is the same either way.

    python3 kautian/build_web_json.py --db kautian/kautian.db --out kautian/web/kautian.web.json
    python3 kautian/build_web_json.py --ktz kautian/opt/v1/kautian.ktz --out kautian.web.json

Serve it with `Content-Encoding: br` — the browser decompresses natively, and
`response.json()` resolves to the document. Precompress at deploy time; brotli
is not in the standard library, so `--brotli-out` needs the `brotli` package and
is only there to report the shipping size:

    python3 kautian/build_web_json.py --db kautian/kautian.db --out k.json --brotli-out k.json.br

This is a projection, not the archive: every row and value survives, but the
schema statements and SQLite header do not, so the .db cannot be rebuilt from
it. Use `build_optimized.py` and `kautian.ktz` for that.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kautian.opt import container, jsonio, webjson


def load_dataset(arguments):
    if arguments.db:
        return container.read_database(arguments.db)
    if arguments.json:
        return jsonio.from_document(jsonio.load(arguments.json))
    return container.dataset(*container.decode(arguments.ktz.read_bytes()))


def write_split(document, directory):
    """Write index.json and one file per table.

    Peak memory in the browser is set by the largest document held at once, not
    by the decoded result, so a client that fetches one table at a time never
    pays for the whole dictionary. `index.json` carries the reading model and
    the table order, which is load-bearing: 詞目 and 義項 must be decoded before
    the tables whose rules join against them.

    It costs about 55 KB compressed against the single file, because each part
    is compressed against its own dictionary instead of a shared one.
    """
    directory.mkdir(parents=True, exist_ok=True)
    written = []

    def emit(name, payload):
        path = directory / name
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        written.append((path, path.stat().st_size))

    for entry in document["tables"]:
        emit(f"{entry['name']}.json", entry)
    emit(
        "index.json",
        {
            "format": document["format"],
            "model": document["model"],
            "tables": [
                {"name": entry["name"], "rows": entry["rows"], "file": f"{entry['name']}.json"}
                for entry in document["tables"]
            ],
        },
    )
    return written


def main(argv=None):
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--db", type=Path, help="read the dataset from a SQLite file")
    source.add_argument("--json", type=Path, help="read the dataset from a KTJSON1 document")
    source.add_argument("--ktz", type=Path, help="read the dataset from a container")
    parser.add_argument("--out", type=Path, help="write the KTWEB1 document as one file")
    parser.add_argument(
        "--split-out",
        type=Path,
        help="write it as index.json plus one file per table, so a client never parses the whole document",
    )
    parser.add_argument("--brotli-out", type=Path, help="also write it brotli-compressed (needs the brotli package)")
    arguments = parser.parse_args(argv)
    if not arguments.out and not arguments.split_out:
        parser.error("nothing to write: pass --out, --split-out, or both")

    document = webjson.to_document(*load_dataset(arguments))

    if arguments.split_out:
        for path, size in write_split(document, arguments.split_out):
            print(f"wrote {path} ({size:,} B)")

    if not arguments.out:
        return 0

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    with open(arguments.out, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {arguments.out} ({arguments.out.stat().st_size:,} B)")

    if arguments.brotli_out:
        try:
            import brotli
        except ImportError:
            print("brotli is not installed; compress at deploy time with `brotli -q 11 --lgwin 24`")
            return 1
        arguments.brotli_out.write_bytes(
            brotli.compress(arguments.out.read_bytes(), quality=11, lgwin=24)
        )
        print(f"wrote {arguments.brotli_out} ({arguments.brotli_out.stat().st_size:,} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
