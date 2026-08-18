#!/usr/bin/env python3
"""
build_web_json.py — Build the Concised browser document: the same entry-less
headword set `build_concised_detail.py` puts in `concised/v3/`, as one KTWEB1
JSON file that decodes with `kautian/web/kautian.mjs` and no other dependency.

Stdlib-only and deterministic: the same two databases produce the same bytes.

    python3 concised/build_web_json.py --kautian-db kautian/kautian.db \
        --concised-db concised/concised.db --out concised/web/concised.web.json

Serve it with `Content-Encoding: br` — the browser decompresses natively and
`response.json()` resolves to the document. Precompress at deploy time; brotli
is not in the standard library, so `--brotli-out` needs the `brotli` package and
is only there to report the shipping size.

This is a projection of the container's contents, not of `concised.db`: only the
headwords 教典 leaves without 義項 are here, and only the columns that carry
content on them. `concised.db` remains the archival form.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from concised.detail import records, source
from kautian import meta
from concised.web import webjson


def build(kautian_db, concised_db):
    """The document, and the records it was built from for the caller to count."""
    headwords, entries, _max_id = source.read(kautian_db, concised_db)
    built = records.build(headwords, entries)
    document = webjson.to_document(built)
    document["meta"] = meta.build({kautian_db.name: kautian_db, concised_db.name: concised_db})
    return document, built


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--kautian-db", required=True, type=Path)
    parser.add_argument("--concised-db", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--brotli-out", type=Path, help="also write it brotli-compressed (needs the brotli package)"
    )
    arguments = parser.parse_args(argv)

    document, built = build(arguments.kautian_db, arguments.concised_db)

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    with open(arguments.out, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
    print(
        f"wrote {arguments.out} ({arguments.out.stat().st_size:,} B) — "
        f"{document['tables'][0]['rows']:,} entries over {len(built):,} headwords"
    )

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
