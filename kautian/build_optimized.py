#!/usr/bin/env python3
"""
build_optimized.py — Pack the kautian dataset into the optimised container, and
verify that unpacking it reproduces the original database byte for byte.

The container is a lossless re-encoding, not a projection: every table, column,
row and NULL survives, and `--verify` rebuilds the SQLite file and compares
SHA-256 against the input. It exists because the .db is 10.26 MB and most of
that is structure a decoder can recompute — denormalised join columns, composed
audio filenames, and romanisation the 漢字 already implies.

The dataset can be read from and written to any of three forms — the SQLite
file, a JSON document, or the container itself — and the compressed bytes are
identical whichever end you start from, because compression only ever sees the
columns.

Stdlib-only. Deterministic: the same dataset always packs to the same bytes.

Usage:
    python3 kautian/build_optimized.py --db kautian/kautian.db --out kautian/opt/v1/kautian.ktz
    python3 kautian/build_optimized.py --db kautian/kautian.db --verify
    python3 kautian/build_optimized.py --db kautian/kautian.db --json-out kautian.json
    python3 kautian/build_optimized.py --json kautian.json --out kautian.ktz --verify kautian/kautian.db
    python3 kautian/build_optimized.py --ktz kautian.ktz --json-out kautian.json --db-out kautian.db
"""

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kautian.meta import sha256
from kautian.opt import container, jsonio


def load_dataset(arguments):
    """Read (schema, columns, header) from whichever source was named."""
    if arguments.db:
        return container.read_database(arguments.db)
    if arguments.json:
        return jsonio.from_document(jsonio.load(arguments.json))
    return container.dataset(*container.decode(arguments.ktz.read_bytes()))


def verify(db_path, blob):
    """Rebuild the database from the container and compare against the original."""
    manifest, columns = container.decode(blob)
    with tempfile.TemporaryDirectory() as workspace:
        rebuilt = Path(workspace) / "rebuilt.db"
        container.rebuild(manifest, columns, rebuilt)
        return sha256(rebuilt), sha256(db_path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--db", type=Path, help="read the dataset from a SQLite file")
    source.add_argument("--json", type=Path, help="read the dataset from a JSON document")
    source.add_argument("--ktz", type=Path, help="read the dataset from a container")
    parser.add_argument("--out", type=Path, help="write the container")
    parser.add_argument("--json-out", type=Path, help="write the dataset as JSON")
    parser.add_argument("--db-out", type=Path, help="write the rebuilt SQLite file")
    parser.add_argument(
        "--verify",
        nargs="?",
        const=True,
        type=Path,
        help="rebuild from the container and compare SHA-256 against this database (defaults to --db)",
    )
    arguments = parser.parse_args(argv)

    reference = arguments.db if arguments.verify is True else arguments.verify
    if arguments.verify and reference is None:
        parser.error("--verify needs a database to compare against when the source is not --db")

    blob = container.encode_dataset(*load_dataset(arguments))
    original = (arguments.db or arguments.json or arguments.ktz).stat().st_size
    print(f"{original:,} B -> {len(blob):,} B ({original / len(blob):.2f}x)")

    if arguments.verify:
        rebuilt_digest, original_digest = verify(reference, blob)
        if rebuilt_digest != original_digest:
            print(f"MISMATCH\n  rebuilt  {rebuilt_digest}\n  original {original_digest}")
            return 1
        print(f"byte-identical, sha256 {original_digest}")

    if arguments.out:
        write(arguments.out, lambda target: target.write_bytes(blob))

    if arguments.json_out or arguments.db_out:
        decoded = container.decode(blob)
        if arguments.json_out:
            write(arguments.json_out, lambda target: jsonio.dump(jsonio.to_document(*decoded), target))
        if arguments.db_out:
            write(arguments.db_out, lambda target: container.rebuild(*decoded, target))
    return 0


def write(path, writer):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    writer(path)
    print(f"wrote {path} ({path.stat().st_size:,} B)")


if __name__ == "__main__":
    raise SystemExit(main())
