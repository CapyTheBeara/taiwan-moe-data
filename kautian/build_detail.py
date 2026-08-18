#!/usr/bin/env python3
"""
build_detail.py — Turn kautian.db into the range-fetchable detail container:
detail.bin (concatenated JSON records), detail.idx (uint16 record lengths over
the whole id space), and meta.json (provenance and integrity constants).

Stdlib-only. Deterministic: detail.bin and detail.idx are byte-identical across
rebuilds of the same database.

Usage:
    python3 kautian/build_detail.py --db kautian/kautian.db --out kautian/v1/
"""

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kautian.detail import container, records, source
from kautian.meta import generator_commit, sha256


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    tables, sense_owner, categories, max_id = source.read(args.db)
    built = records.build(tables, sense_owner, categories)
    provenance = {
        "dbSha256": sha256(args.db),
        "generatorCommit": generator_commit(Path(__file__).resolve().parent.parent),
        "buildDate": datetime.date.today().isoformat(),
    }
    meta = container.write(built, max_id, args.out, provenance)
    print(f"{meta['liveIds']} records, {meta['containerBytes']} B, max id {max_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
