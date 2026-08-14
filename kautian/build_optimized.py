#!/usr/bin/env python3
"""
build_optimized.py — Pack kautian.db into the optimised container, and verify
that unpacking it reproduces the original database byte for byte.

The container is a lossless re-encoding, not a projection: every table, column,
row and NULL survives, and `--verify` rebuilds the SQLite file and compares
SHA-256 against the input. It exists because the .db is 10.26 MB and most of
that is structure a decoder can recompute — denormalised join columns, composed
audio filenames, and romanisation the 漢字 already implies.

Stdlib-only. Deterministic: the same database always packs to the same bytes.

Usage:
    python3 kautian/build_optimized.py --db kautian/kautian.db --out kautian/opt/v1/kautian.ktz
    python3 kautian/build_optimized.py --db kautian/kautian.db --verify
"""

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kautian.opt import container


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(db_path, blob):
    """Rebuild the database from the container and compare against the original."""
    manifest, columns = container.decode(blob)
    with tempfile.TemporaryDirectory() as workspace:
        rebuilt = Path(workspace) / "rebuilt.db"
        container.rebuild(manifest, columns, rebuilt)
        return sha256(rebuilt), sha256(db_path)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args(argv)

    blob = container.encode(arguments.db)
    original = arguments.db.stat().st_size
    print(f"{original:,} B -> {len(blob):,} B ({original / len(blob):.2f}x)")

    if arguments.verify:
        rebuilt_digest, original_digest = verify(arguments.db, blob)
        if rebuilt_digest != original_digest:
            print(f"MISMATCH\n  rebuilt  {rebuilt_digest}\n  original {original_digest}")
            return 1
        print(f"byte-identical, sha256 {original_digest}")

    if arguments.out:
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        arguments.out.write_bytes(blob)
        print(f"wrote {arguments.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
